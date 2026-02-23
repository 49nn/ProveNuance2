"""Komenda: pn2 assumptions — listowanie założeń z bazy danych."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from pn2._db import get_connection

console = Console(width=200)

DOMAIN_STYLE: dict[str, str] = {
    "generic":    "cyan",
    "e-commerce": "yellow",
    "event":      "green",
}

TYPE_STYLE: dict[str, str] = {
    "data_contract":        "blue",
    "data_semantics":       "cyan",
    "enumeration":          "yellow",
    "closed_world":         "magenta",
    "external_computation": "red",
    "conflict_resolution":  "bright_red",
    "missing_predicate":    "bright_yellow",
}

QUERY = """
    SELECT id, fragment_id, source_type, source_id,
           about_pred, about_atom_index, about_arg_index, about_const,
           type, text, domain
    FROM assumption
    {where}
    ORDER BY domain, fragment_id, source_type, source_id, about_pred, type
"""


def run(args: argparse.Namespace) -> None:
    conditions: list[str] = []

    if args.domain:
        doms = ", ".join(f"'{d}'" for d in args.domain)
        conditions.append(f"domain IN ({doms})")
    if args.type:
        typs = ", ".join(f"'{t}'" for t in args.type)
        conditions.append(f"type IN ({typs})")
    if args.pred:
        conditions.append(f"about_pred ILIKE '%{args.pred}%'")
    if args.source:
        conditions.append(f"source_type = '{args.source}'")
    if args.fragment:
        conditions.append(f"fragment_id ILIKE '%{args.fragment}%'")
    if args.search:
        conditions.append(f"text ILIKE '%{args.search}%'")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = QUERY.format(where=where)

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia:[/red] {e}")
        raise SystemExit(1)

    with conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    if not rows:
        console.print("[yellow]Brak założeń spełniających kryteria.[/yellow]")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("ID",       no_wrap=True, justify="right", style="dim")
    table.add_column("FRAGMENT", no_wrap=True, max_width=20)
    table.add_column("SOURCE",   no_wrap=True, max_width=24)
    table.add_column("PRED",     no_wrap=True, max_width=30)
    table.add_column("CONST",    no_wrap=True, max_width=20)
    table.add_column("TYPE",     no_wrap=True)
    table.add_column("DOMAIN",   no_wrap=True)
    table.add_column("TEXT",     no_wrap=False, max_width=80)

    for (
        row_id, fragment_id, source_type, source_id,
        about_pred, about_atom_index, about_arg_index, about_const,
        atype, text, domain,
    ) in rows:
        source_txt = Text()
        source_txt.append(source_type, style="bold" if source_type == "rule" else "italic")
        source_txt.append(f"/{source_id}", style="")

        pred_txt = Text(about_pred)
        if about_atom_index is not None:
            pred_txt.append(f"[{about_atom_index}]", style="dim")
        if about_arg_index is not None:
            pred_txt.append(f":{about_arg_index}", style="dim")

        type_txt   = Text(atype, style=TYPE_STYLE.get(atype, ""))
        domain_txt = Text(domain, style=DOMAIN_STYLE.get(domain, ""))
        const_txt  = about_const or Text("", style="dim")

        table.add_row(
            str(row_id),
            fragment_id,
            source_txt,
            pred_txt,
            const_txt,
            type_txt,
            domain_txt,
            text,
        )

    total = len(rows)
    console.print()
    console.print(table)
    n = total
    _pl = "założenie" if n == 1 else ("założenia" if 2 <= n % 10 <= 4 and n % 100 not in range(11, 15) else "założeń")
    console.print(f"  [dim]{n} {_pl}[/dim]\n")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "assumptions",
        help="Listuje założenia (ScopedAssumptions) odkryte przez ekstraktor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje założenia scoped zapisane w bazie przez pn2 extract.

Typy założeń:
  data_contract        — system musi dostarczyć fakty w tej formie
  data_semantics       — znaczenie statusu / pola / stałej
  enumeration          — wymagany słownik wartości
  closed_world         — założenie NAF / domknięcia świata
  external_computation — coś liczone poza Horniem
  conflict_resolution  — rozstrzyganie sprzecznych wniosków
  missing_predicate    — obejście braku predykatu

Przykłady:
  pn2 assumptions
  pn2 assumptions --domain event
  pn2 assumptions --type enumeration
  pn2 assumptions --pred delivery_status
  pn2 assumptions --source rule
  pn2 assumptions --fragment art18
  pn2 assumptions --search "musi być"
        """,
    )
    p.add_argument(
        "--domain", "-d",
        nargs="+",
        metavar="DOMAIN",
        choices=["generic", "e-commerce", "event"],
        help="Filtruj po domenie (można podać kilka).",
    )
    p.add_argument(
        "--type", "-t",
        nargs="+",
        metavar="TYPE",
        choices=[
            "data_contract", "data_semantics", "enumeration", "closed_world",
            "external_computation", "conflict_resolution", "missing_predicate",
        ],
        help="Filtruj po typie założenia (można podać kilka).",
    )
    p.add_argument(
        "--pred",
        metavar="PRED",
        help="Filtruj po about_pred (ILIKE, np. delivery_status).",
    )
    p.add_argument(
        "--source",
        metavar="SOURCE",
        choices=["rule", "condition"],
        help="Filtruj po źródle: rule | condition.",
    )
    p.add_argument(
        "--fragment",
        metavar="ID",
        help="Filtruj po fragment_id (ILIKE).",
    )
    p.add_argument(
        "--search", "-s",
        metavar="TEKST",
        help="Szukaj w treści założenia (ILIKE).",
    )
    p.set_defaults(func=run)
