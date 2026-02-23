"""Komenda: pn2 constants — listowanie stałych z bazy danych."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from pn2._db import get_connection

console = Console(width=180)

DOMAIN_STYLE: dict[str, str] = {
    "generic":    "cyan",
    "e-commerce": "yellow",
    "event":      "green",
}

QUERY = """
    SELECT value, meaning_pl, domain, notes
    FROM constant
    {where}
    ORDER BY domain, value
"""


def run(args: argparse.Namespace) -> None:
    conditions: list[str] = []
    if args.domain:
        doms = ", ".join(f"'{d}'" for d in args.domain)
        conditions.append(f"domain IN ({doms})")
    if args.search:
        conditions.append(
            f"(value ILIKE '%{args.search}%' OR meaning_pl ILIKE '%{args.search}%')"
        )
    if args.no_meaning:
        conditions.append("meaning_pl IS NULL")

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
        console.print("[yellow]Brak stałych spełniających kryteria.[/yellow]")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("VALUE",      style="bold", no_wrap=True)
    table.add_column("DOMAIN",     no_wrap=True)
    table.add_column("MEANING_PL", no_wrap=False, max_width=60)
    table.add_column("NOTES",      no_wrap=False, max_width=30)

    for value, meaning_pl, domain, notes in rows:
        domain_txt  = Text(domain, style=DOMAIN_STYLE.get(domain, ""))
        meaning_txt = meaning_pl or Text("—", style="dim")
        notes_txt   = notes or ""
        table.add_row(value, domain_txt, meaning_txt, notes_txt)

    total = len(rows)
    console.print()
    console.print(table)
    console.print(
        f"  [dim]{total} sta{'łe' if 2 <= total % 10 <= 4 and total % 100 not in range(11,15) else 'łych' if total != 1 else 'ła'}[/dim]\n"
    )


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "constants",
        help="Listuje stałe domenowe odkryte przez ekstraktor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje stałe (ground terms) zapisane w bazie przez pn2 extract.

Przykłady:
  pn2 constants
  pn2 constants --domain event
  pn2 constants --no-meaning
  pn2 constants --search confirmed
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
        "--search", "-s",
        metavar="TEKST",
        help="Szukaj w value lub meaning_pl (ILIKE).",
    )
    p.add_argument(
        "--no-meaning",
        action="store_true",
        help="Pokaż tylko stałe bez opisu (meaning_pl IS NULL).",
    )
    p.set_defaults(func=run)
