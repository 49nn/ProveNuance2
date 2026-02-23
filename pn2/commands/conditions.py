"""Komenda: pn2 conditions — listowanie warunków nazwanych z bazy danych."""

from __future__ import annotations

import argparse
import json

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

QUERY = """
    SELECT id, meaning_pl, required_facts, optional_facts, domain, notes
    FROM condition
    {where}
    ORDER BY domain, id
"""


def _fmt_atoms(facts_json, detail: bool) -> str:
    if isinstance(facts_json, str):
        facts = json.loads(facts_json)
    else:
        facts = facts_json or []
    if not facts:
        return Text("—", style="dim")
    if detail:
        parts = []
        for a in facts:
            neg  = "not " if a.get("negated") else ""
            pred = a.get("pred", "?")
            args = ", ".join(a.get("args", []))
            parts.append(f"{neg}{pred}({args})")
        return "\n".join(parts)
    return f"{len(facts)} atom{'y' if 2 <= len(facts) % 10 <= 4 else 'ów' if len(facts) != 1 else ''}"


def run(args: argparse.Namespace) -> None:
    conditions: list[str] = []

    if args.domain:
        doms = ", ".join(f"'{d}'" for d in args.domain)
        conditions.append(f"domain IN ({doms})")
    if args.search:
        conditions.append(
            f"(id ILIKE '%{args.search}%' OR meaning_pl ILIKE '%{args.search}%')"
        )
    if args.no_meaning:
        conditions.append("meaning_pl IS NULL OR meaning_pl = ''")

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
        console.print("[yellow]Brak warunków spełniających kryteria.[/yellow]")
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("ID",        no_wrap=True, style="bold", max_width=30)
    table.add_column("DOMAIN",    no_wrap=True)
    table.add_column("MEANING_PL",no_wrap=False, max_width=50)
    table.add_column("REQUIRED",  no_wrap=False, max_width=50)
    table.add_column("OPTIONAL",  no_wrap=False, max_width=30)

    for cond_id, meaning_pl, required_facts, optional_facts, domain, notes in rows:
        domain_txt   = Text(domain, style=DOMAIN_STYLE.get(domain, ""))
        meaning_txt  = meaning_pl or Text("—", style="dim")
        required_txt = _fmt_atoms(required_facts, detail=args.detail)
        optional_txt = _fmt_atoms(optional_facts, detail=args.detail)

        table.add_row(cond_id, domain_txt, meaning_txt, required_txt, optional_txt)

    total = len(rows)
    console.print()
    console.print(table)
    _pl = "warunek" if total == 1 else ("warunki" if 2 <= total % 10 <= 4 and total % 100 not in range(11, 15) else "warunków")
    console.print(f"  [dim]{total} {_pl}[/dim]\n")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "conditions",
        help="Listuje warunki nazwane (ConditionDefinition) odkryte przez ekstraktor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje warunki zapisane w bazie przez pn2 extract (pole new_conditions).
Warunki są globalnie unikalne po id i używane w meets_condition/2.

Przykłady:
  pn2 conditions
  pn2 conditions --domain event
  pn2 conditions --search buyer
  pn2 conditions --detail
  pn2 conditions --no-meaning
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
        help="Szukaj w id lub meaning_pl (ILIKE).",
    )
    p.add_argument(
        "--no-meaning",
        action="store_true",
        help="Pokaż tylko warunki bez opisu.",
    )
    p.add_argument(
        "--detail",
        action="store_true",
        help="Wyświetl pełną listę atomów required/optional.",
    )
    p.set_defaults(func=run)
