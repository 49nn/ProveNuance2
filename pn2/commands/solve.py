"""Komenda: pn2 solve — uruchamia solver Datalog na regułach z bazy."""

from __future__ import annotations

import argparse
import pathlib
import sys

from rich.console import Console
from rich.table   import Table
from rich         import box
from rich.text    import Text

from pn2._db import get_connection

console = Console(width=200)


# ---------------------------------------------------------------------------
# Wyświetlanie wyników
# ---------------------------------------------------------------------------

def _show_goal_result(goal_str: str, pred: str, goal_args: tuple, evaluator) -> None:
    from solver.engine import _unify

    console.print(f"\nZapytanie: [bold cyan]{goal_str}[/bold cyan]")
    results = evaluator.query(pred, goal_args)

    if not results:
        console.print("  [red]FAŁSZ[/red] — brak podstawień")
        return

    has_vars = any(a.startswith("?") for a in goal_args)
    if not has_vars:
        console.print("  [green]PRAWDA[/green]")
        return

    console.print(f"  [green]PRAWDA[/green] — {len(results)} podstawień:")
    vars_sorted = sorted(results[0].keys())
    table = Table(box=box.SIMPLE_HEAD, header_style="bold white", show_header=True)
    for var in vars_sorted:
        table.add_column(var, style="cyan", no_wrap=True)
    for r in results:
        table.add_row(*[r.get(v, "?") for v in vars_sorted])
    console.print(table)


def _show_derived_facts(all_facts: dict, edb: dict) -> None:
    """Wyświetla fakty pochodne (IDB minus EDB)."""
    derived: dict[str, set] = {}
    for pred, args_set in all_facts.items():
        new_args = args_set - edb.get(pred, set())
        if new_args:
            derived[pred] = new_args

    if not derived:
        console.print("\n[yellow]Brak faktów pochodnych (IDB).[/yellow]")
        return

    console.print("\n[bold]Fakty pochodne (IDB):[/bold]")
    table = Table(box=box.SIMPLE_HEAD, header_style="bold white", show_header=True)
    table.add_column("PREDYKAT", style="bold cyan", no_wrap=True)
    table.add_column("ARGUMENTY", no_wrap=False)
    for pred in sorted(derived):
        for args in sorted(derived[pred]):
            table.add_row(pred, ", ".join(args))
    console.print(table)
    console.print(f"  [dim]{sum(len(v) for v in derived.values())} faktów w {len(derived)} predykatach[/dim]")


def _print_horn(rules: list, edb_facts: dict, all_facts: dict) -> None:
    """Drukuje pełne rozumowanie jako klauzule Horna na stdout (plain text)."""
    out: list[str] = []

    # ── EDB ──────────────────────────────────────────────────────────────────
    out.append("% ===== EDB (fakty wejściowe) =====")
    for pred in sorted(edb_facts):
        for args in sorted(edb_facts[pred]):
            if args:
                out.append(f"{pred}({', '.join(args)}).")
            else:
                out.append(f"{pred}.")
    out.append("")

    # ── REGUŁY ───────────────────────────────────────────────────────────────
    out.append("% ===== REGUŁY IDB =====")
    for rule in rules:
        if rule.prov_unit:
            units_str = ", ".join(f"§{u}" for u in rule.prov_unit)
            out.append(f"% [{rule.rule_id}] {units_str}")
        if rule.prov_quote:
            q = rule.prov_quote[:120].replace("\n", " ")
            out.append(f'% "{q}"')

        head_args_str = ", ".join(rule.head_args)
        head = f"{rule.head_pred}({head_args_str})" if head_args_str else rule.head_pred

        if rule.body:
            body_atoms: list[str] = []
            for atom in rule.body:
                atom_args_str = ", ".join(atom.args)
                atom_s = f"{atom.pred}({atom_args_str})" if atom_args_str else atom.pred
                if atom.negated:
                    atom_s = f"not {atom_s}"
                body_atoms.append(atom_s)
            body_str = ",\n    ".join(body_atoms)
            out.append(f"{head} :-\n    {body_str}.")
        else:
            out.append(f"{head}.")
        out.append("")

    # ── FAKTY POCHODNE ───────────────────────────────────────────────────────
    out.append("% ===== FAKTY POCHODNE (IDB \\ EDB) =====")
    derived: dict[str, set] = {}
    for pred, args_set in all_facts.items():
        new_args = args_set - edb_facts.get(pred, set())
        if new_args:
            derived[pred] = new_args

    if not derived:
        out.append("% (brak)")
    else:
        for pred in sorted(derived):
            for args in sorted(derived[pred]):
                if args:
                    out.append(f"{pred}({', '.join(args)}).")
                else:
                    out.append(f"{pred}.")

    output = "\n".join(out) + "\n"
    try:
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.buffer.flush()
    except AttributeError:
        print(output, end="")


def _show_strata(strata: dict[str, int]) -> None:
    """Wyświetla warstwy stratyfikacji."""
    console.print("\n[bold]Stratyfikacja:[/bold]")
    by_stratum: dict[int, list[str]] = {}
    for pred, s in sorted(strata.items()):
        by_stratum.setdefault(s, []).append(pred)
    for s in sorted(by_stratum):
        preds_str = ", ".join(sorted(by_stratum[s]))
        style = "green" if s == 0 else "yellow" if s == 1 else "red"
        console.print(f"  Warstwa {s}: [{style}]{preds_str}[/{style}]")


# ---------------------------------------------------------------------------
# Główna logika
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    from solver import (
        Evaluator,
        load_facts_json,
        load_rules_from_db,
        load_derived_rules_from_db,
        load_conditions_from_db,
        parse_goal,
    )

    # 1. Wczytaj fakty EDB
    facts_path = pathlib.Path(args.facts)
    if not facts_path.exists():
        console.print(f"[red]Brak pliku faktów:[/red] {facts_path}")
        raise SystemExit(1)

    try:
        case_id, file_domain, edb_facts = load_facts_json(facts_path)
    except Exception as e:
        console.print(f"[red]Błąd wczytywania faktów:[/red] {e}")
        raise SystemExit(1)

    domain = args.domain or file_domain or "generic"
    n_edb  = sum(len(v) for v in edb_facts.values())
    console.print(
        f"Fakty EDB: [bold]{facts_path.name}[/bold]  "
        f"case=[cyan]{case_id or '—'}[/cyan]  "
        f"domena=[cyan]{domain}[/cyan]  "
        f"{n_edb} faktów ({len(edb_facts)} predykatów)"
    )

    # 2. Wczytaj reguły i warunki z bazy
    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    fragment = args.fragment or None
    include_derived: bool = getattr(args, "include_derived", False)
    try:
        rules      = load_rules_from_db(conn, domain=domain, fragment_id=fragment)
        conditions = load_conditions_from_db(conn)
        if include_derived:
            derived_rules = load_derived_rules_from_db(conn, domain=domain, fragment_id=fragment)
        else:
            derived_rules = []
    except Exception as e:
        console.print(f"[red]Błąd ładowania z bazy:[/red] {e}")
        conn.close()
        raise SystemExit(1)
    finally:
        conn.close()

    manifest_rules = rules  # zachowaj oddzielnie do fallbacku
    if include_derived and derived_rules:
        console.print(
            f"Reguły IDB:  [bold]{len(rules)}[/bold] manifest + "
            f"[bold]{len(derived_rules)}[/bold] derived  "
            f"(domena={domain}"
            + (f", fragment={fragment}" if fragment else "")
            + f")   Warunki: [bold]{len(conditions)}[/bold]"
        )
        rules = rules + derived_rules
    else:
        console.print(
            f"Reguły IDB:  [bold]{len(rules)}[/bold]  "
            f"(domena={domain}"
            + (f", fragment={fragment}" if fragment else "")
            + f")   Warunki: [bold]{len(conditions)}[/bold]"
        )

    if not rules:
        console.print("[yellow]Brak reguł — solver nie ma co obliczać.[/yellow]")
        if args.show_derived:
            _show_derived_facts(edb_facts, edb_facts)
        return

    # 3. Zbuduj ewaluator i uruchom
    try:
        ev = Evaluator(rules=rules, facts=edb_facts, conditions=conditions)
    except ValueError as e:
        if include_derived and derived_rules:
            console.print(f"[yellow]Ostrzeżenie stratyfikacji:[/yellow] {e}")
            console.print(
                f"[yellow]Reguły derived ({len(derived_rules)}) powodują konflikt — "
                f"solver uruchomiony wyłącznie z regułami manifestu ({len(manifest_rules)}).[/yellow]"
            )
            rules = manifest_rules
            try:
                ev = Evaluator(rules=rules, facts=edb_facts, conditions=conditions)
            except ValueError as e2:
                console.print(f"[red]Błąd stratyfikacji (manifest):[/red] {e2}")
                raise SystemExit(1)
        else:
            console.print(f"[red]Błąd stratyfikacji:[/red] {e}")
            raise SystemExit(1)

    if args.show_strata:
        _show_strata(ev.strata)

    try:
        all_facts = ev.evaluate()
    except ValueError as e:
        console.print(f"[red]Błąd ewaluacji:[/red] {e}")
        raise SystemExit(1)

    n_idb = sum(len(v) for v in all_facts.values()) - n_edb
    console.print(f"Ewaluacja zakończona: [green]{n_idb}[/green] nowych faktów pochodnych")

    # 4. Odpowiedzi na cele / wydruk Horn
    if getattr(args, "print_horn", False):
        _print_horn(rules, edb_facts, all_facts)

    goals_raw: list[str] = args.goal or []
    if goals_raw:
        for goal_str in goals_raw:
            try:
                pred, goal_args = parse_goal(goal_str)
            except ValueError as e:
                console.print(f"[red]Błąd parsowania celu:[/red] {e}")
                continue
            _show_goal_result(goal_str, pred, goal_args, ev)
    elif not getattr(args, "print_horn", False):
        _show_derived_facts(all_facts, edb_facts)


# ---------------------------------------------------------------------------
# Rejestracja parsera
# ---------------------------------------------------------------------------

def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "solve",
        help="Uruchamia solver Datalog na regułach z bazy i faktach z pliku JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Wczytuje fakty EDB z pliku JSON i reguły IDB z bazy danych,
uruchamia ewaluację Datalog (bottom-up, stratified NAF) i odpowiada na pytania.

Format pliku faktów JSON:
  {
    "case_id": "sprawa-001",
    "domain":  "event",
    "facts": [
      {"pred": "delivery_status", "args": ["ord-1", "confirmed"]},
      {"pred": "order_amount",    "args": ["ord-1", "150"]}
    ]
  }

Przykłady:
  pn2 solve --facts sprawa.json
  pn2 solve --facts sprawa.json --goal "auction(?O)"
  pn2 solve --facts sprawa.json --goal "eligible_bidder(?P, ?O)" --domain event
  pn2 solve --facts sprawa.json --goal "is_valid" --show-strata
  pn2 solve --facts sprawa.json --fragment art18 --goal "auction(?O)"
        """,
    )
    p.add_argument(
        "--facts", "-f",
        metavar="PLIK",
        required=True,
        help="Plik JSON z faktami EDB dla konkretnego przypadku.",
    )
    p.add_argument(
        "--goal", "-g",
        metavar="CEL",
        action="append",
        help="Cel zapytania, np. 'auction(?O)'. Można podać wielokrotnie.",
    )
    p.add_argument(
        "--domain", "-d",
        metavar="DOMAIN",
        choices=["generic", "e-commerce", "event"],
        help="Domena reguł (domyślnie: z pliku faktów).",
    )
    p.add_argument(
        "--fragment",
        metavar="FRAGMENT_ID",
        help="Ogranicz reguły do konkretnego fragmentu (fragment_id).",
    )
    p.add_argument(
        "--show-strata",
        action="store_true",
        help="Wyświetl podział predykatów na warstwy stratyfikacji.",
    )
    p.add_argument(
        "--show-derived",
        action="store_true",
        help="Zawsze wyświetl wszystkie fakty pochodne (IDB), nawet gdy podano --goal.",
    )
    p.add_argument(
        "--include-derived",
        action="store_true",
        dest="include_derived",
        help="Uwzględnij reguły z tabeli derived_rule (odkryte automatycznie) obok reguł manifestu.",
    )
    p.add_argument(
        "--print-horn",
        action="store_true",
        dest="print_horn",
        help=(
            "Wydrukuj pełne rozumowanie jako klauzule Horna (EDB + reguły + fakty pochodne). "
            "Można łączyć z --goal."
        ),
    )
    p.set_defaults(func=run)
