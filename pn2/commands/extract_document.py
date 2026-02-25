"""Komenda: pn2 extract-document — ekstrakcja reguł Horn dla wszystkich spanów dokumentu."""

from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table   import Table
from rich         import box

from pn2._db import get_connection

console = Console()

_MIN_CONTENT_LENGTH = 80  # spany krótsze niż to są pomijane domyślnie


# ---------------------------------------------------------------------------
# Ładowanie spanów z bazy
# ---------------------------------------------------------------------------

def _load_spans(conn, doc_id: str, level: int | None, unit: str | None, min_len: int) -> list[dict]:
    """Zwraca listę spanów do przetworzenia (jako słowniki)."""
    wheres = ["doc_id = %s", "length(content) >= %s"]
    params: list = [doc_id, min_len]

    if level is not None:
        wheres.append("level = %s")
        params.append(level)
    if unit:
        wheres.append("unit = %s")
        params.append(unit)

    sql = (
        "SELECT unit, title, content, level, page_start, page_end "
        "FROM document_span "
        "WHERE " + " AND ".join(wheres) +
        " ORDER BY id"
    )

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            "unit":       r[0],
            "title":      r[1],
            "content":    r[2],
            "level":      r[3],
            "page_start": r[4],
            "page_end":   r[5],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Ekstrakcja jednego spanu
# ---------------------------------------------------------------------------

def _fragment_id(doc_id: str, unit: str) -> str:
    """Tworzy fragment_id z doc_id i unit (bezpieczny dla bazy)."""
    safe_unit = unit.replace(" ", "_").replace("/", "-").replace("\\", "-")[:60]
    return f"{doc_id}___{safe_unit}"


def _extract_span(
    span:    dict,
    doc_id:  str,
    domain:  str,
    model:   str,
    conditions_txt: str,
    show_prompt: bool,
) -> dict | None:
    """
    Buduje prompt, wysyła do Gemini, parsuje odpowiedź.
    Ustawia result['fragment_id'] na podstawie doc_id + unit.
    Zwraca sparsowany dict lub None przy błędzie.
    """
    from llm_query import build_prompt, call_gemini
    import json

    # Buduj fragment: tytuł + treść
    fragment_text = f"[Jednostka: {span['unit']}, strony {span['page_start']}–{span['page_end']}]\n"
    fragment_text += f"{span['title']}\n\n{span['content']}"

    try:
        prompt = build_prompt(domain, conditions_txt, fragment_text)
    except Exception as e:
        console.print(f"    [red]Błąd budowania promptu:[/red] {e}")
        return None

    if show_prompt:
        print(prompt)

    try:
        raw = call_gemini(prompt, model=model)
    except Exception as e:
        console.print(f"    [red]Błąd Gemini API:[/red] {e}")
        return None

    # Parsuj JSON
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    try:
        result = json.loads(text)
    except Exception as e:
        console.print(f"    [red]Błąd parsowania JSON:[/red] {e}")
        console.print(f"    [dim]{raw[:200]}[/dim]")
        return None

    # Nadpisz fragment_id — nie ufamy LLM w tym polu
    result["fragment_id"] = _fragment_id(doc_id, span["unit"])
    return result


# ---------------------------------------------------------------------------
# Zapis wyników
# ---------------------------------------------------------------------------

def _save_result(result: dict, domain: str) -> dict[str, int]:
    """Zapisuje wszystkie dane z jednego wyniku ekstrakcji. Zwraca liczniki."""
    from llm_query import (
        collect_rules,              upsert_rules,
        collect_conditions,         upsert_conditions,
        collect_constants,          upsert_constants,
        collect_assumptions,        upsert_assumptions,
        collect_derived_predicates, upsert_derived_predicates,
    )

    counts = {"rules": 0, "conditions": 0, "constants": 0, "assumptions": 0, "derived_predicates": 0}

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"    [red]Błąd połączenia:[/red] {e}")
        return counts

    try:
        rules = collect_rules(result)
        if rules:
            counts["rules"] = upsert_rules(conn, rules, domain)

        derived = collect_derived_predicates(rules)
        if derived:
            counts["derived_predicates"] = upsert_derived_predicates(conn, derived, domain)

        conds = collect_conditions(result)
        if conds:
            counts["conditions"] = upsert_conditions(conn, conds, domain)

        constants = collect_constants(result)
        if constants:
            counts["constants"] = upsert_constants(conn, constants, domain)

        assumptions = collect_assumptions(result)
        if assumptions:
            counts["assumptions"] = upsert_assumptions(conn, assumptions, domain)

        conn.commit()
    except Exception as e:
        conn.rollback()
        console.print(f"    [red]Błąd zapisu do bazy:[/red] {e}")
    finally:
        conn.close()

    return counts


# ---------------------------------------------------------------------------
# Główna logika
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    from llm_query import read_conditions, DEFAULT_MODEL

    conditions_txt = read_conditions(args.conditions)
    domain         = args.domain
    model          = args.model or DEFAULT_MODEL

    # Pobierz spany
    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    spans = _load_spans(conn, args.doc_id, args.level, args.unit, args.min_length)
    conn.close()

    if not spans:
        console.print(
            f"[yellow]Brak spanów dla doc_id='{args.doc_id}'"
            + (f" level={args.level}" if args.level else "")
            + f" min_length={args.min_length}[/yellow]"
        )
        raise SystemExit(0)

    console.print(
        f"Dokument: [bold]{args.doc_id}[/bold]  "
        f"domena=[cyan]{domain}[/cyan]  "
        f"model=[cyan]{model}[/cyan]  "
        f"spanów do przetworzenia: [bold]{len(spans)}[/bold]"
    )

    # Tryb podglądu (--dry-run)
    if args.dry_run:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold white", show_header=True)
        table.add_column("UNIT",  style="cyan", no_wrap=True)
        table.add_column("LVL",   justify="right", style="dim")
        table.add_column("STRONY", justify="center", style="dim")
        table.add_column("LEN",   justify="right", style="dim")
        table.add_column("TYTUŁ", max_width=60)
        for s in spans:
            pages = (
                str(s["page_start"])
                if s["page_start"] == s["page_end"]
                else f"{s['page_start']}–{s['page_end']}"
            )
            table.add_row(
                s["unit"][:40], str(s["level"]), pages,
                str(len(s["content"])), s["title"][:60],
            )
        console.print(table)
        console.print(f"[dim](--dry-run: nie wysyłam do Gemini)[/dim]")
        return

    # Ekstrakcja
    total_counts: dict[str, int] = {"rules": 0, "conditions": 0, "constants": 0, "assumptions": 0, "derived_predicates": 0}
    errors = 0

    for i, span in enumerate(spans, 1):
        frag_id = _fragment_id(args.doc_id, span["unit"])
        pages   = (
            str(span["page_start"])
            if span["page_start"] == span["page_end"]
            else f"{span['page_start']}–{span['page_end']}"
        )
        console.print(
            f"[{i}/{len(spans)}] [bold cyan]{span['unit'][:50]}[/bold cyan]"
            f"  str.{pages}  {len(span['content'])} znaków"
        )

        result = _extract_span(span, args.doc_id, domain, model, conditions_txt, args.show_prompt)
        if result is None:
            errors += 1
        else:
            counts = _save_result(result, domain)
            for k, v in counts.items():
                total_counts[k] += v

            parts = []
            if counts["rules"]:               parts.append(f"[green]{counts['rules']} reguł[/green]")
            if counts["derived_predicates"]:  parts.append(f"[green]{counts['derived_predicates']} pred.pochodnych[/green]")
            if counts["conditions"]:          parts.append(f"[cyan]{counts['conditions']} warunków[/cyan]")
            if counts["constants"]:           parts.append(f"[yellow]{counts['constants']} stałych[/yellow]")
            if counts["assumptions"]:         parts.append(f"[magenta]{counts['assumptions']} założeń[/magenta]")
            console.print("    → " + (", ".join(parts) if parts else "[dim]brak wyników[/dim]"))

        # Opóźnienie między wywołaniami (rate limiting)
        if i < len(spans) and args.delay > 0:
            time.sleep(args.delay)

    # Podsumowanie
    console.print()
    status = "[green]Gotowe[/green]" if errors == 0 else f"[yellow]Gotowe z {errors} błędami[/yellow]"
    console.print(
        f"{status} — łącznie: "
        f"{total_counts['rules']} reguł, "
        f"{total_counts['derived_predicates']} pred.pochodnych, "
        f"{total_counts['conditions']} warunków, "
        f"{total_counts['constants']} stałych, "
        f"{total_counts['assumptions']} założeń"
    )


# ---------------------------------------------------------------------------
# Rejestracja parsera
# ---------------------------------------------------------------------------

def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "extract-document",
        help="Ekstrakcja reguł Horn dla wszystkich spanów dokumentu.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Iteruje przez spany dokumentu (z tabeli document_span) i dla każdego wywołuje
ekstraktor reguł Horn (Gemini). Wyniki są zapisywane do bazy (upsert).

fragment_id reguł jest ustawiany jako <doc_id>___<unit> (nie z odpowiedzi LLM).

Przykłady:
  pn2 extract-document --doc-id Regulamin --domain event
  pn2 extract-document --doc-id Regulamin --domain event --level 1
  pn2 extract-document --doc-id Regulamin --domain event --dry-run
  pn2 extract-document --doc-id Regulamin --domain event --unit "1." --show-prompt
  pn2 extract-document --doc-id Regulamin --domain event --delay 3 --min-length 200
        """,
    )
    p.add_argument(
        "--doc-id", "-D",
        metavar="ID",
        required=True,
        help="Identyfikator dokumentu (doc_id w tabeli document_span).",
    )
    p.add_argument(
        "--domain", "-d",
        default="generic",
        choices=["generic", "e-commerce", "event"],
        help="Domena predykatów (domyślnie: generic).",
    )
    p.add_argument(
        "--level", "-l",
        type=int,
        metavar="N",
        help="Przetwarzaj tylko spany o podanym poziomie hierarchii.",
    )
    p.add_argument(
        "--unit", "-u",
        metavar="UNIT",
        help="Przetwarzaj tylko span o podanej jednostce (np. '1.').",
    )
    p.add_argument(
        "--min-length",
        type=int,
        default=_MIN_CONTENT_LENGTH,
        metavar="N",
        help=f"Pomiń spany krótsze niż N znaków (domyślnie: {_MIN_CONTENT_LENGTH}).",
    )
    p.add_argument(
        "--conditions", "-c",
        metavar="PLIK",
        help="Plik JSON ze słownikiem warunków (domyślnie: pusty).",
    )
    p.add_argument(
        "--model", "-m",
        metavar="MODEL",
        help="Model Gemini.",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SEK",
        help="Opóźnienie (sekundy) między wywołaniami API (domyślnie: 1.0).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko pokaż które spany byłyby przetworzone, nie wywołuj Gemini.",
    )
    p.add_argument(
        "--show-prompt",
        action="store_true",
        help="Wypisz fragment promptu przed każdym wywołaniem.",
    )
    p.set_defaults(func=run)
