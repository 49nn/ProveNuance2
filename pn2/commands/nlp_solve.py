"""Komenda: pn2 nlp-solve — ekstrakcja faktów z tekstu NL + solver + interpretacja."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Optional

from rich.console import Console
from rich.table   import Table
from rich         import box
from rich.panel   import Panel

from pn2._db import get_connection

console = Console(width=200)

_ROOT                = pathlib.Path(__file__).resolve().parent.parent.parent
EXTRACTOR_TEMPLATE   = _ROOT / "templates-schemas" / "prompt-nlp-extractor.md"
INTERPRETER_TEMPLATE = _ROOT / "templates-schemas" / "prompt-interpreter.md"


# ---------------------------------------------------------------------------
# Wczytywanie wejścia
# ---------------------------------------------------------------------------

def _read_input_text(args: argparse.Namespace) -> str:
    """Wczytuje tekst przypadku z --text, --input-file lub stdin."""
    if args.text:
        return args.text.strip()
    if args.input_file:
        p = pathlib.Path(args.input_file)
        if not p.exists():
            console.print(f"[red]Brak pliku wejściowego:[/red] {p}")
            raise SystemExit(1)
        return p.read_text(encoding="utf-8").strip()
    # stdin
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            return text
    console.print("[red]Brak tekstu wejściowego.[/red] Podaj --text, --input-file lub przekaż tekst przez stdin.")
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Parsowanie JSON z LLM
# ---------------------------------------------------------------------------

def _parse_llm_json(raw: str, label: str = "LLM") -> Optional[dict]:
    """
    Usuwa otoczkę ```json / ``` i parsuje JSON.
    Przy błędzie drukuje skrócony podgląd odpowiedzi i zwraca None.
    """
    text = raw.strip()
    # Usuń markdown fences
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[: text.rfind("```")].rstrip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        preview = raw[:500].replace("\n", " ")
        console.print(f"[red]Błąd parsowania JSON ({label}):[/red] {e}")
        console.print(f"  Podgląd odpowiedzi: [dim]{preview}[/dim]")
        return None


# ---------------------------------------------------------------------------
# Ładowanie szablonu
# ---------------------------------------------------------------------------

def _load_template(path: pathlib.Path) -> str:
    """Wczytuje szablon i usuwa otoczkę ```text / ```."""
    body = path.read_text(encoding="utf-8").strip()
    if body.startswith("```text"):
        body = body[len("```text"):].lstrip("\n")
    if body.endswith("```"):
        body = body[: body.rfind("```")].rstrip()
    return body


# ---------------------------------------------------------------------------
# Budowanie promptu ekstrakcji
# ---------------------------------------------------------------------------

def _build_extraction_prompt(domain: str, case_text: str) -> str:
    """Buduje prompt ekstrakcji faktów z tekstu NL."""
    from llm_query.prompt import fetch_predicates_for_nlp, fetch_constants

    if not EXTRACTOR_TEMPLATE.exists():
        raise FileNotFoundError(f"Brak szablonu ekstrakcji: {EXTRACTOR_TEMPLATE}")

    predicates      = fetch_predicates_for_nlp(domain)
    predicates_json = json.dumps(predicates, ensure_ascii=False, indent=2)
    constants       = fetch_constants(domain)
    constants_json  = json.dumps(constants, ensure_ascii=False, indent=2)
    body            = _load_template(EXTRACTOR_TEMPLATE)

    return (
        body
        .replace("{{DOMAIN}}",            domain)
        .replace("{{PREDICATE_CATALOG}}", predicates_json)
        .replace("{{KNOWN_CONSTANTS}}",   constants_json)
        .replace("{{CASE_TEXT}}",         case_text)
    )


# ---------------------------------------------------------------------------
# Walidacja wyekstrahowanych faktów
# ---------------------------------------------------------------------------

def _validate_extracted_facts(data: dict) -> tuple[bool, list[str]]:
    """
    Sprawdza podstawowy format wyekstrahowanych faktów.
    Zwraca (is_valid, lista_ostrzeżeń).
    """
    warnings: list[str] = []

    if not isinstance(data, dict):
        return False, ["Odpowiedź LLM nie jest obiektem JSON."]

    facts = data.get("facts")
    if facts is None:
        return False, ["Brak klucza 'facts' w odpowiedzi LLM."]
    if not isinstance(facts, list):
        return False, ["Klucz 'facts' nie jest listą."]

    for i, f in enumerate(facts):
        if not isinstance(f, dict):
            warnings.append(f"Fakt #{i} nie jest obiektem — pomijam.")
            continue
        if "pred" not in f:
            warnings.append(f"Fakt #{i} nie ma klucza 'pred' — pomijam.")
        if "args" not in f:
            warnings.append(f"Fakt #{i} nie ma klucza 'args' — pomijam.")
        elif not isinstance(f["args"], list):
            warnings.append(f"Fakt #{i}.args nie jest listą — pomijam.")

    return True, warnings


# ---------------------------------------------------------------------------
# Formatowanie wyników solvera dla promptu interpretacji
# ---------------------------------------------------------------------------

def _format_derived_for_llm(
    all_facts: dict,
    edb: dict,
    goal_results: list[tuple[str, list[dict]]],
) -> tuple[str, str]:
    """
    Konwertuje wyniki solvera do tekstu dla promptu interpretacji.
    Zwraca (derived_facts_text, goal_results_text).
    """
    # Fakty pochodne
    derived: dict[str, list] = {}
    for pred, args_set in all_facts.items():
        new_args = args_set - edb.get(pred, set())
        if new_args:
            derived[pred] = sorted(new_args)

    if derived:
        lines = []
        for pred in sorted(derived):
            for args in derived[pred]:
                args_str = ", ".join(args)
                lines.append(f"  {pred}({args_str})")
        derived_text = "\n".join(lines)
    else:
        derived_text = "  (brak faktów pochodnych)"

    # Wyniki zapytań — header jest w szablonie, tu tylko treść
    if not goal_results:
        goals_text = "(nie podano zapytań)"
    else:
        lines = []
        for goal_str, results in goal_results:
            if not results:
                lines.append(f"  {goal_str} → FAŁSZ (brak podstawień)")
            else:
                has_vars = any(k.startswith("?") for k in results[0].keys()) if results else False
                if not has_vars or not results[0]:
                    lines.append(f"  {goal_str} → PRAWDA")
                else:
                    lines.append(f"  {goal_str} → PRAWDA ({len(results)} podstawień):")
                    for r in results[:10]:  # max 10
                        subst = ", ".join(f"{k}={v}" for k, v in sorted(r.items()))
                        lines.append(f"    [{subst}]")
                    if len(results) > 10:
                        lines.append(f"    ... (i {len(results) - 10} więcej)")
        goals_text = "\n".join(lines)

    return derived_text, goals_text


# ---------------------------------------------------------------------------
# Formatowanie proweniencji reguł dla promptu interpretacji
# ---------------------------------------------------------------------------

def _format_rule_provenance(rules: list, derived_preds: set) -> str:
    """
    Buduje blok proweniencji dla reguł, których głowa należy do
    faktycznie wyprowadzonych predykatów. Pomija reguły bez cytatu.

    Format każdego wpisu:
        [R1] eligible_bidder — §3.1(b), §3.2
          "Uprawniony jest każdy zarejestrowany uczestnik..."
    """
    lines: list[str] = []
    for rule in rules:
        if rule.head_pred not in derived_preds:
            continue
        quote = (rule.prov_quote or "").strip()
        if not quote:
            continue
        units_str = ", ".join(f"§{u}" for u in rule.prov_unit) if rule.prov_unit else "§?"
        lines.append(f"[{rule.rule_id}] {rule.head_pred} — {units_str}")
        lines.append(f'  "{quote}"')
        lines.append("")
    return "\n".join(lines).rstrip() if lines else "  (brak proweniencji)"


# ---------------------------------------------------------------------------
# Budowanie promptu interpretacji
# ---------------------------------------------------------------------------

def _build_interpretation_prompt(
    domain: str,
    original_text: str,
    extracted_facts_json: str,
    derived_facts_text: str,
    goal_results_text: str,
    provenance_text: str = "",
) -> str:
    """Buduje prompt interpretacji wyników solvera."""
    from llm_query.prompt import fetch_predicates_for_nlp

    if not INTERPRETER_TEMPLATE.exists():
        raise FileNotFoundError(f"Brak szablonu interpretacji: {INTERPRETER_TEMPLATE}")

    predicates      = fetch_predicates_for_nlp(domain)
    predicates_json = json.dumps(predicates, ensure_ascii=False, indent=2)
    body            = _load_template(INTERPRETER_TEMPLATE)

    return (
        body
        .replace("{{DOMAIN}}",            domain)
        .replace("{{PREDICATE_CATALOG}}", predicates_json)
        .replace("{{ORIGINAL_TEXT}}",     original_text)
        .replace("{{EXTRACTED_FACTS}}",   extracted_facts_json)
        .replace("{{DERIVED_FACTS}}",     derived_facts_text)
        .replace("{{RULE_PROVENANCE}}",   provenance_text or "  (brak proweniencji)")
        .replace("{{GOAL_RESULTS}}",      goal_results_text)
    )


# ---------------------------------------------------------------------------
# Główna logika
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    from solver import (
        Evaluator,
        load_rules_from_db,
        load_conditions_from_db,
        parse_goal,
    )
    from llm_query import call_gemini, DEFAULT_MODEL
    from pn2.commands.solve import _show_derived_facts, _show_goal_result, _show_strata

    domain = args.domain or "generic"
    model  = args.model or DEFAULT_MODEL
    extract_model   = getattr(args, "extract_model",   None) or model
    interpret_model = getattr(args, "interpret_model", None) or model

    # ── Faza 1: Ekstrakcja faktów z tekstu NL ──────────────────────────────

    case_text = _read_input_text(args)

    console.print(f"\n[bold cyan]Faza 1:[/bold cyan] Ekstrakcja faktów z tekstu ({len(case_text)} znaków)")

    try:
        extraction_prompt = _build_extraction_prompt(domain, case_text)
    except (FileNotFoundError, Exception) as e:
        console.print(f"[red]Błąd budowania promptu ekstrakcji:[/red] {e}")
        raise SystemExit(1)

    if args.show_prompt:
        console.print(Panel(
            extraction_prompt[:1000] + ("…" if len(extraction_prompt) > 1000 else ""),
            title="Prompt ekstrakcji faktów",
            border_style="blue",
            expand=False,
        ))

    console.print(f"  Wysyłam do Gemini ([dim]{extract_model}[/dim])…")
    try:
        raw_extraction = call_gemini(extraction_prompt, model=extract_model)
    except Exception as e:
        console.print(f"[red]Błąd Gemini API (ekstrakcja):[/red] {e}")
        raise SystemExit(1)

    extracted = _parse_llm_json(raw_extraction, label="ekstrakcja faktów")
    if extracted is None:
        raise SystemExit(1)

    is_valid, warnings = _validate_extracted_facts(extracted)
    for w in warnings:
        console.print(f"  [yellow][warn][/yellow] {w}")
    if not is_valid:
        console.print("[red]Wyekstrahowane fakty mają nieprawidłowy format — przerywam.[/red]")
        raise SystemExit(1)

    # Zbuduj słownik faktów EDB
    case_id     = extracted.get("case_id") or "nlp-case"
    file_domain = extracted.get("domain") or domain
    notes       = extracted.get("extraction_notes", "")

    edb_facts: dict[str, set[tuple]] = {}
    for f in extracted.get("facts", []):
        if not isinstance(f, dict) or "pred" not in f or "args" not in f:
            continue
        if not isinstance(f["args"], list):
            continue
        pred       = str(f["pred"])
        args_tuple = tuple(str(a) for a in f["args"])
        edb_facts.setdefault(pred, set()).add(args_tuple)

    n_edb = sum(len(v) for v in edb_facts.values())
    console.print(
        f"  Wyekstrahowano: case=[cyan]{case_id}[/cyan]  "
        f"domena=[cyan]{file_domain}[/cyan]  "
        f"[bold]{n_edb}[/bold] faktów ({len(edb_facts)} predykatów)"
    )
    if notes:
        console.print(f"  [dim]Uwagi LLM: {notes}[/dim]")

    if args.show_extracted_facts:
        if edb_facts:
            table = Table(box=box.SIMPLE_HEAD, header_style="bold white", show_header=True)
            table.add_column("PREDYKAT", style="bold cyan", no_wrap=True)
            table.add_column("ARGUMENTY")
            for pred in sorted(edb_facts):
                for a in sorted(edb_facts[pred]):
                    table.add_row(pred, ", ".join(a))
            console.print(table)
        else:
            console.print("  [yellow]Brak wyekstrahowanych faktów.[/yellow]")

    # ── Faza 2: Solver Datalog ─────────────────────────────────────────────

    console.print(f"\n[bold cyan]Faza 2:[/bold cyan] Solver Datalog")

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    fragment = getattr(args, "fragment", None)
    try:
        rules      = load_rules_from_db(conn, domain=file_domain, fragment_id=fragment)
        conditions = load_conditions_from_db(conn)
    except Exception as e:
        console.print(f"[red]Błąd ładowania z bazy:[/red] {e}")
        conn.close()
        raise SystemExit(1)
    finally:
        conn.close()

    console.print(
        f"  Reguły IDB: [bold]{len(rules)}[/bold]  "
        f"(domena={file_domain}"
        + (f", fragment={fragment}" if fragment else "")
        + f")   Warunki: [bold]{len(conditions)}[/bold]"
    )

    if not rules:
        console.print("[yellow]Brak reguł — solver nie ma co obliczać.[/yellow]")
        _show_derived_facts(edb_facts, edb_facts)
        return

    try:
        ev = Evaluator(rules=rules, facts=edb_facts, conditions=conditions)
    except ValueError as e:
        console.print(f"[red]Błąd stratyfikacji:[/red] {e}")
        raise SystemExit(1)

    if getattr(args, "show_strata", False):
        _show_strata(ev.strata)

    try:
        all_facts = ev.evaluate()
    except ValueError as e:
        console.print(f"[red]Błąd ewaluacji:[/red] {e}")
        raise SystemExit(1)

    n_idb = sum(len(v) for v in all_facts.values()) - n_edb
    console.print(f"  Ewaluacja zakończona: [green]{n_idb}[/green] nowych faktów pochodnych")

    # Wyświetl wyniki
    goals_raw: list[str] = args.goal or []
    goal_results: list[tuple[str, list[dict]]] = []

    if goals_raw:
        for goal_str in goals_raw:
            try:
                pred, goal_args = parse_goal(goal_str)
            except ValueError as e:
                console.print(f"[red]Błąd parsowania celu:[/red] {e}")
                continue
            results = ev.query(pred, goal_args)
            goal_results.append((goal_str, results))
            _show_goal_result(goal_str, pred, goal_args, ev)
    else:
        _show_derived_facts(all_facts, edb_facts)

    # ── Faza 3: Interpretacja wyników ──────────────────────────────────────

    if getattr(args, "no_interpret", False):
        return

    console.print(f"\n[bold cyan]Faza 3:[/bold cyan] Interpretacja wyników")

    derived_text, goals_text = _format_derived_for_llm(all_facts, edb_facts, goal_results)
    extracted_facts_json = json.dumps(extracted.get("facts", []), ensure_ascii=False, indent=2)

    # Predykaty faktycznie wyprowadzone przez solver (IDB \ EDB)
    derived_preds: set[str] = {
        pred
        for pred, args_set in all_facts.items()
        if args_set - edb_facts.get(pred, set())
    }
    provenance_text = _format_rule_provenance(rules, derived_preds)

    try:
        interp_prompt = _build_interpretation_prompt(
            domain               = file_domain,
            original_text        = case_text,
            extracted_facts_json = extracted_facts_json,
            derived_facts_text   = derived_text,
            goal_results_text    = goals_text,
            provenance_text      = provenance_text,
        )
    except Exception as e:
        console.print(f"[yellow][warn] Błąd budowania promptu interpretacji:[/yellow] {e}")
        return

    if args.show_prompt:
        console.print(Panel(
            interp_prompt[:1000] + ("…" if len(interp_prompt) > 1000 else ""),
            title="Prompt interpretacji",
            border_style="blue",
            expand=False,
        ))

    console.print(f"  Wysyłam do Gemini ([dim]{interpret_model}[/dim])…")
    try:
        raw_interp = call_gemini(interp_prompt, model=interpret_model)
    except Exception as e:
        console.print(f"[yellow][warn] Błąd Gemini API (interpretacja):[/yellow] {e}")
        return

    # Interpretacja to narracja — nie JSON; drukujemy bezpośrednio.
    # Normalizujemy końce linii (API może zwracać \r\n), scalamy pojedyncze
    # złamania wiersza w obrębie akapitu w spację, zachowując granice akapitów.
    import re
    text = raw_interp.strip().replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = re.split(r"\n{2,}", text)
    normalized = "\n\n".join(
        re.sub(r"\n+", " ", p.strip()) for p in paragraphs if p.strip()
    )
    console.print(normalized, markup=False, highlight=False)


# ---------------------------------------------------------------------------
# Rejestracja parsera
# ---------------------------------------------------------------------------

def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "nlp-solve",
        help="Ekstrakcja faktów z tekstu NL, solver Datalog i interpretacja wyników.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Trójfazowy pipeline NLP → Datalog → NL:
  Faza 1: Ekstrakcja faktów z tekstu w języku naturalnym (Gemini → JSON).
  Faza 2: Solver Datalog na wyekstrahowanych faktach i regułach z bazy.
  Faza 3: Interpretacja wyników w języku naturalnym (Gemini → opis).

Przykłady:
  pn2 nlp-solve --text "Jan Kowalski zarejestrował się na Akademię Managera..." --domain event
  pn2 nlp-solve -f opis_sprawy.txt --domain event --goal "registration_status(?R, 'confirmed')"
  echo "..." | pn2 nlp-solve --domain event --show-extracted-facts
  pn2 nlp-solve --text "..." --domain event --no-interpret --show-strata
        """,
    )
    p.add_argument(
        "--text",
        metavar="TEKST",
        help="Tekst opisu przypadku (inline).",
    )
    p.add_argument(
        "--input-file", "-f",
        metavar="PLIK",
        dest="input_file",
        help="Plik tekstowy z opisem przypadku.",
    )
    p.add_argument(
        "--domain", "-d",
        metavar="DOMAIN",
        choices=["generic", "e-commerce", "event"],
        default="generic",
        help="Domena predykatów i reguł (domyślnie: generic).",
    )
    p.add_argument(
        "--goal", "-g",
        metavar="CEL",
        action="append",
        help="Cel zapytania, np. 'registration_status(?R, confirmed)'. Można podać wielokrotnie.",
    )
    p.add_argument(
        "--fragment",
        metavar="FRAGMENT_ID",
        help="Ogranicz reguły do konkretnego fragmentu (fragment_id).",
    )
    p.add_argument(
        "--model", "-m",
        metavar="MODEL",
        help="Model Gemini dla obu faz LLM (domyślnie: gemini-2.5-flash).",
    )
    p.add_argument(
        "--extract-model",
        metavar="MODEL",
        dest="extract_model",
        help="Nadpisz model Gemini wyłącznie dla fazy 1 (ekstrakcja faktów).",
    )
    p.add_argument(
        "--interpret-model",
        metavar="MODEL",
        dest="interpret_model",
        help="Nadpisz model Gemini wyłącznie dla fazy 3 (interpretacja).",
    )
    p.add_argument(
        "--show-extracted-facts",
        action="store_true",
        dest="show_extracted_facts",
        help="Wyświetl tabelę wyekstrahowanych faktów EDB po fazie 1.",
    )
    p.add_argument(
        "--show-prompt",
        action="store_true",
        dest="show_prompt",
        help="Wyświetl prompty przed wysłaniem do Gemini.",
    )
    p.add_argument(
        "--show-strata",
        action="store_true",
        dest="show_strata",
        help="Wyświetl warstwy stratyfikacji solvera.",
    )
    p.add_argument(
        "--no-interpret",
        action="store_true",
        dest="no_interpret",
        help="Pomiń fazę 3 (interpretacja w języku naturalnym).",
    )
    p.set_defaults(func=run)
