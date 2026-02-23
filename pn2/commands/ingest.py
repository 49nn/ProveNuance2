"""Komenda: pn2 ingest — parsowanie PDF do spanów sekcji."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

from data_model.documents import DocumentSpan, SpanTree

console = Console()


# ---------------------------------------------------------------------------
# Zapis do JSON
# ---------------------------------------------------------------------------

def _write_json(spans: SpanTree, json_path: Path) -> None:
    data = [asdict(s) for s in spans]
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]JSON:[/green] {json_path}  ({len(spans)} spanów)")


# ---------------------------------------------------------------------------
# Zapis do bazy danych
# ---------------------------------------------------------------------------

_UPSERT_SQL = """
    INSERT INTO document_span
        (doc_id, unit, title, content, level, parent_unit, page_start, page_end)
    VALUES %s
    ON CONFLICT (doc_id, unit) DO UPDATE SET
        title      = EXCLUDED.title,
        content    = EXCLUDED.content,
        level      = EXCLUDED.level,
        parent_unit= EXCLUDED.parent_unit,
        page_start = EXCLUDED.page_start,
        page_end   = EXCLUDED.page_end
"""


def _write_db(spans: SpanTree, doc_id: str) -> None:
    from pn2._db import get_connection
    import psycopg2.extras

    if not spans:
        console.print("[yellow]Brak spanów do zapisania w bazie.[/yellow]")
        return

    rows = [
        (
            doc_id,
            s.unit,
            s.title,
            s.content,
            s.level,
            s.parent_unit,
            s.page_start,
            s.page_end,
        )
        for s in spans
    ]

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    with conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, _UPSERT_SQL, rows)

    console.print(f"[green]DB:[/green] upsert {len(spans)} spanów dla doc_id='{doc_id}'")


# ---------------------------------------------------------------------------
# Wyświetlanie w terminalu
# ---------------------------------------------------------------------------

def _show_table(spans: SpanTree) -> None:
    if not spans:
        console.print("[yellow]Brak spanów.[/yellow]")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("LVL",   justify="right", no_wrap=True, style="dim")
    table.add_column("UNIT",  no_wrap=True, style="bold cyan")
    table.add_column("PARENT", no_wrap=True, style="dim")
    table.add_column("STRONY", justify="center", no_wrap=True)
    table.add_column("LEN",   justify="right", no_wrap=True)
    table.add_column("TYTUŁ", no_wrap=False, max_width=50)

    for span in spans:
        indent = "  " * (span.level - 1)
        pages = (
            str(span.page_start)
            if span.page_start == span.page_end
            else f"{span.page_start}–{span.page_end}"
        )
        table.add_row(
            str(span.level),
            indent + span.unit,
            span.parent_unit or "-",
            pages,
            str(len(span.content)),
            span.title[:80],
        )

    console.print()
    console.print(table)
    console.print(f"  [dim]{len(spans)} spanów[/dim]\n")


# ---------------------------------------------------------------------------
# Główna logika komendy
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    pdf_path = Path(args.pdf_file)
    if not pdf_path.exists():
        console.print(f"[red]Plik nie istnieje:[/red] {pdf_path}")
        raise SystemExit(1)
    if pdf_path.suffix.lower() != ".pdf":
        console.print(f"[red]Oczekiwano pliku .pdf, otrzymano:[/red] {pdf_path.suffix}")
        raise SystemExit(1)

    doc_id: str = args.doc_id or pdf_path.stem

    console.print(f"Parsowanie [bold]{pdf_path}[/bold] (doc_id=[cyan]{doc_id}[/cyan]) …")

    try:
        from pdf.parser import parse_pdf
        spans = parse_pdf(pdf_path, doc_id)
    except ImportError as e:
        console.print(f"[red]Błąd importu (brak PyMuPDF?):[/red] {e}")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Błąd parsowania:[/red] {e}")
        raise SystemExit(1)

    console.print(f"Znaleziono [bold]{len(spans)}[/bold] spanów.")

    out = args.out  # "json" | "db" | "both"

    if out in ("json", "both"):
        json_path = pdf_path.with_suffix("").with_suffix(f".spans.json")
        _write_json(spans, json_path)

    if out in ("db", "both"):
        _write_db(spans, doc_id)

    if args.show:
        _show_table(spans)


# ---------------------------------------------------------------------------
# Rejestracja parsera
# ---------------------------------------------------------------------------

def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "ingest",
        help="Parsuje PDF na spany sekcji i zapisuje do JSON / bazy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Parsuje dokument PDF na spany sekcji (DocumentSpan) i zapisuje wynik.

Przykłady:
  pn2 ingest dokument.pdf --show
  pn2 ingest dokument.pdf --out json
  pn2 ingest dokument.pdf --out db --show
  pn2 ingest dokument.pdf --doc-id umowa_2024 --out both
        """,
    )
    p.add_argument(
        "pdf_file",
        metavar="PLIK.pdf",
        help="Ścieżka do pliku PDF.",
    )
    p.add_argument(
        "--doc-id",
        metavar="ID",
        default=None,
        help="Identyfikator dokumentu (domyślnie: nazwa pliku bez .pdf).",
    )
    p.add_argument(
        "--out",
        choices=["json", "db", "both"],
        default="both",
        help="Cel zapisu: json, db lub both (domyślnie: both).",
    )
    p.add_argument(
        "--show",
        action="store_true",
        help="Wyświetl tabelę spanów w terminalu po zapisie.",
    )
    p.set_defaults(func=run)
