"""Komenda: pn2 derived-predicates — listowanie predykatów pochodnych z bazy."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from pn2._db import get_connection

console = Console(width=220)

DOMAIN_STYLE: dict[str, str] = {
    "generic":    "cyan",
    "e-commerce": "yellow",
    "event":      "green",
}

QUERY = """
    SELECT
        name,
        arity,
        pred,
        signature,
        domain,
        source_fragment_id,
        meaning_pl
    FROM derived_predicate
    {where}
    ORDER BY domain, name
"""


def run(args: argparse.Namespace) -> None:
    conditions: list[str] = []

    if args.domain:
        doms = ", ".join(f"'{d}'" for d in args.domain)
        conditions.append(f"domain IN ({doms})")
    if args.fragment:
        conditions.append(f"source_fragment_id ILIKE '%{args.fragment}%'")
    if args.search:
        conditions.append(
            f"(name ILIKE '%{args.search}%' OR meaning_pl ILIKE '%{args.search}%')"
        )

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
        console.print("[yellow]Brak predykatów pochodnych spełniających kryteria.[/yellow]")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )

    table.add_column("PRED",      style="bold", no_wrap=True)
    table.add_column("DOMAIN",    no_wrap=True)
    table.add_column("FRAGMENT",  no_wrap=True, max_width=24)
    table.add_column("ARITY",     justify="right", no_wrap=True)
    table.add_column("SIGNATURE", no_wrap=True)
    table.add_column("MEANING",   no_wrap=False, max_width=60)

    for name, arity, pred, signature, domain, fragment_id, meaning_pl in rows:
        domain_txt = Text(domain, style=DOMAIN_STYLE.get(domain, ""))
        sig_txt    = ", ".join(signature) if signature else ""
        mean_txt   = meaning_pl or ""

        table.add_row(
            pred,
            domain_txt,
            fragment_id or "",
            str(arity),
            sig_txt,
            mean_txt,
        )

    total = len(rows)
    console.print()
    console.print(table)
    _pl = (
        "predykat pochodny"
        if total == 1
        else (
            "predykaty pochodne"
            if 2 <= total % 10 <= 4 and total % 100 not in range(11, 15)
            else "predykatów pochodnych"
        )
    )
    console.print(f"  [dim]{total} {_pl}[/dim]\n")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "derived-predicates",
        help="Listuje predykaty pochodne odkryte automatycznie przez ekstraktor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje predykaty pochodne (io=derived, kind=auto_discovered) odkryte
przez ekstraktor jako głowy reguł Horn, zapisane w tabeli derived_predicate.

Kolumny:
  PRED      – identyfikator name/arity
  DOMAIN    – domena
  FRAGMENT  – fragment, z którego pochodzi pierwsze odkrycie
  ARITY     – liczba argumentów
  SIGNATURE – typy argumentów (domyślnie: any)
  MEANING   – wygenerowany opis po polsku

Przykłady:
  pn2 derived-predicates
  pn2 derived-predicates --domain event
  pn2 derived-predicates --fragment art18
  pn2 derived-predicates --search eligible
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
        "--fragment",
        metavar="ID",
        help="Filtruj po source_fragment_id (ILIKE).",
    )
    p.add_argument(
        "--search", "-s",
        metavar="TEKST",
        help="Szukaj w nazwie lub opisie (ILIKE).",
    )
    p.set_defaults(func=run)
