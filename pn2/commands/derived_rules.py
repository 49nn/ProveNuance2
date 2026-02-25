"""Komenda: pn2 derived-rules - listowanie regul Horn z tabeli derived_rule."""

from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from pn2._db import get_connection

console = Console(width=220)

DOMAIN_STYLE: dict[str, str] = {
    "generic": "cyan",
    "e-commerce": "yellow",
    "event": "green",
}

QUERY = """
    SELECT fragment_id, rule_id, head_pred, head_args, body, domain, notes
    FROM derived_rule
    {where}
    ORDER BY domain, fragment_id, rule_id
"""


def _fmt_atom(atom: dict) -> str:
    pred = atom.get("pred", "?")
    args = [str(a) for a in atom.get("args", [])]
    neg = "not " if atom.get("negated") else ""
    return f"{neg}{pred}({', '.join(args)})"


def _fmt_head(head_pred: str, head_args) -> str:
    if isinstance(head_args, str):
        head_args = json.loads(head_args)
    return f"{head_pred}({', '.join(str(a) for a in head_args)})"


def _fmt_body(body, detail: bool, max_width: int = 100) -> str:
    if isinstance(body, str):
        body = json.loads(body)
    if not body:
        return "[dim](fakt)[/dim]"
    atoms = [_fmt_atom(a) for a in body]
    if detail:
        return ",\n  ".join(atoms)
    joined = ", ".join(atoms)
    if len(joined) > max_width:
        return joined[:max_width] + "..."
    return joined


def _fmt_rule_horn(head_pred: str, head_args, body) -> str:
    head = _fmt_head(head_pred, head_args)
    if isinstance(body, str):
        body = json.loads(body)
    if not body:
        return f"{head}."
    atoms = ", ".join(_fmt_atom(a) for a in body)
    return f"{head} :-\n  {atoms}."


def _print_horn(rows: list) -> None:
    import sys

    for _fragment_id, _rule_id, head_pred, head_args, body, _domain, _notes in rows:
        print(_fmt_rule_horn(head_pred, head_args, body), file=sys.stdout)


def run(args: argparse.Namespace) -> None:
    conditions: list[str] = []

    if args.domain:
        doms = ", ".join(f"'{d}'" for d in args.domain)
        conditions.append(f"domain IN ({doms})")
    if args.fragment:
        conditions.append(f"fragment_id ILIKE '%{args.fragment}%'")
    if args.pred:
        conditions.append(f"head_pred ILIKE '%{args.pred}%'")
    if args.search:
        conditions.append(
            f"(head_pred ILIKE '%{args.search}%' OR notes ILIKE '%{args.search}%')"
        )

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = QUERY.format(where=where)

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Blad polaczenia:[/red] {e}")
        raise SystemExit(1)

    with conn, conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    if not rows:
        console.print("[yellow]Brak regul pochodnych spelniajacych kryteria.[/yellow]")
        return

    if getattr(args, "horn", False):
        _print_horn(rows)
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )
    table.add_column("FRAGMENT", no_wrap=True, max_width=20)
    table.add_column("ID", no_wrap=True, max_width=24, style="bold")
    table.add_column("HEAD", no_wrap=True, max_width=40)
    table.add_column("BODY", no_wrap=False, max_width=90)
    table.add_column("DOM", no_wrap=True)

    for fragment_id, rule_id, head_pred, head_args, body, domain, _notes in rows:
        head_txt = _fmt_head(head_pred, head_args)
        body_txt = _fmt_body(body, detail=args.detail)
        domain_txt = Text(domain, style=DOMAIN_STYLE.get(domain, ""))

        table.add_row(fragment_id, rule_id, head_txt, body_txt, domain_txt)

    total = len(rows)
    console.print()
    console.print(table)
    plural = (
        "regula"
        if total == 1
        else (
            "reguly"
            if 2 <= total % 10 <= 4 and total % 100 not in range(11, 15)
            else "regul"
        )
    )
    console.print(f"  [dim]{total} {plural} pochodnych[/dim]\n")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "derived-rules",
        help="Listuje reguly Horna odkryte automatycznie przez ekstraktor.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje reguly Horna odkryte przez ekstraktor i zapisane w tabeli derived_rule.

Przyklady:
  pn2 derived-rules
  pn2 derived-rules --domain event
  pn2 derived-rules --fragment art18
  pn2 derived-rules --pred auction
  pn2 derived-rules --detail
        """,
    )
    p.add_argument(
        "--domain",
        "-d",
        nargs="+",
        metavar="DOMAIN",
        choices=["generic", "e-commerce", "event"],
        help="Filtruj po domenie (mozna podac kilka).",
    )
    p.add_argument(
        "--fragment",
        metavar="ID",
        help="Filtruj po fragment_id (ILIKE).",
    )
    p.add_argument(
        "--pred",
        metavar="PRED",
        help="Filtruj po predykacie glowy (ILIKE).",
    )
    p.add_argument(
        "--search",
        "-s",
        metavar="TEKST",
        help="Szukaj w head_pred lub notes (ILIKE).",
    )
    p.add_argument(
        "--detail",
        action="store_true",
        help="Wyswietl pelne cialo reguly (kazdy atom w osobnej linii).",
    )
    p.add_argument(
        "--horn",
        action="store_true",
        help="Wypisz reguly w skladni Horn (head :- body.) bez tabelki.",
    )
    p.set_defaults(func=run)
