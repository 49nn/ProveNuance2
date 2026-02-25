"""Komenda: pn2 ingest-url — pobiera stronę HTML i parsuje do spanów sekcji."""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

from rich.console import Console

from pn2.commands.ingest import _show_table, _write_db, _write_json

console = Console()


def _doc_id_from_url(url: str) -> str:
    """Generuje domyślny doc_id z URL (host + path jako slug ASCII)."""
    parsed = urlparse(url)
    host = parsed.netloc.replace(".", "-").replace(":", "-")
    path = parsed.path.strip("/").replace("/", "-")
    raw = f"{host}-{path}" if path else host
    raw = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    raw = re.sub(r"[^\w-]", "-", raw).strip("-")
    raw = re.sub(r"-{2,}", "-", raw)
    return raw[:80] or "url-doc"


def _load_parse_html_url():
    """
    Importuje parser HTML.

    Fallback: dla stalej instalacji editable (pn2.exe), ktora nie widzi nowego
    pakietu html_parser, dodajemy katalog projektu do sys.path i probujemy ponownie.
    """
    try:
        from html_parser.parser import parse_html_url
        return parse_html_url
    except ModuleNotFoundError as e:
        if e.name != "html_parser":
            raise
        project_root = Path(__file__).resolve().parents[2]
        project_root_str = str(project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)
        from html_parser.parser import parse_html_url
        return parse_html_url


def run(args: argparse.Namespace) -> None:
    url: str = args.url
    doc_id: str = args.doc_id or _doc_id_from_url(url)

    console.print(f"Pobieranie [bold]{url}[/bold] (doc_id=[cyan]{doc_id}[/cyan]) …")

    try:
        parse_html_url = _load_parse_html_url()
        spans = parse_html_url(url, doc_id)
    except ImportError as e:
        console.print(f"[red]Błąd importu (brak requests lub beautifulsoup4?):[/red] {e}")
        if isinstance(e, ModuleNotFoundError):
            if e.name == "bs4":
                console.print("[yellow]Zainstaluj:[/yellow] pip install beautifulsoup4")
            elif e.name == "requests":
                console.print("[yellow]Zainstaluj:[/yellow] pip install requests")
            elif e.name == "html_parser":
                console.print(
                    "[yellow]Napraw instalacje editable pakietu:[/yellow] "
                    "pip install -e ."
                )
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Błąd pobierania/parsowania:[/red] {e}")
        raise SystemExit(1)

    console.print(f"Znaleziono [bold]{len(spans)}[/bold] spanów.")

    out = args.out

    if out in ("json", "both"):
        safe_name = re.sub(r"[^\w-]", "-", doc_id)
        _write_json(spans, Path(f"{safe_name}.spans.json"))

    if out in ("db", "both"):
        _write_db(spans, doc_id)

    if args.show:
        _show_table(spans)


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "ingest-url",
        help="Pobiera stronę HTML i parsuje ją na spany sekcji (h1–h6, div, p itp.).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Pobiera stronę HTML pod podanym URL i parsuje ją na spany sekcji (DocumentSpan).

Podział na spany:
  - nagłówki h1–h6 tworzą granice sekcji (hierarchia poziomów)
  - elementy p, div, li itp. dostarczają treści bieżącego spanu
  - treść przed pierwszym nagłówkiem trafia do spanu "intro"

Przykłady:
  pn2 ingest-url https://example.com/regulamin --show
  pn2 ingest-url https://example.com/page --doc-id regulamin --out db
  pn2 ingest-url https://example.com/page --out json --show
        """,
    )
    p.add_argument(
        "url",
        metavar="URL",
        help="Adres URL strony HTML do pobrania.",
    )
    p.add_argument(
        "--doc-id",
        metavar="ID",
        default=None,
        help="Identyfikator dokumentu (domyślnie: generowany z URL).",
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
