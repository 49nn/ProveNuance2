"""Komenda: pn2 predicates — listowanie predykatów z bazy."""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text

from pn2._db import get_connection

console = Console(width=220)

# Kolory per kind
KIND_STYLE: dict[str, str] = {
    "domain":    "cyan",
    "condition": "yellow",
    "decision":  "green",
    "ui":        "magenta",
    "audit":     "red",
    "builtin":   "dim white",
}

# Kolory per io
IO_STYLE: dict[str, str] = {
    "input":   "blue",
    "derived": "green",
    "both":    "yellow",
}

QUERY = """
    SELECT
        p.name,
        p.arity,
        p.pred,
        p.signature,
        p.io::text,
        p.kind::text,
        p.meaning_pl,
        p.allowed_in_head,
        p.allowed_in_body,
        p.allowed_in_negated_body,
        p.value_domain_allowed_values,
        mp.naf_closed_world_predicates
    FROM predicate p
    CROSS JOIN manifest_policy mp
    {where}
    ORDER BY p.kind, p.name
"""


def _allowed_flags(head: bool, body: bool, neg: bool) -> str:
    parts = []
    if head:
        parts.append("H")
    if body:
        parts.append("B")
    if neg:
        parts.append("!B")
    return "/".join(parts) if parts else "-"


def run(args: argparse.Namespace) -> None:
    # Buduj WHERE
    conditions: list[str] = []
    if args.kind:
        kinds = ", ".join(f"'{k}'" for k in args.kind)
        conditions.append(f"p.kind::text IN ({kinds})")
    if args.io:
        ios = ", ".join(f"'{i}'" for i in args.io)
        conditions.append(f"p.io::text IN ({ios})")
    if args.search:
        conditions.append(
            f"(p.name ILIKE '%{args.search}%' OR p.meaning_pl ILIKE '%{args.search}%')"
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
        console.print("[yellow]Brak predykatów spełniających kryteria.[/yellow]")
        return

    naf_set: set[str] = set(rows[0][11]) if rows[0][11] else set()

    # Tabela
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold white",
        row_styles=["", "dim"],
        expand=False,
    )

    table.add_column("PRED",       style="bold", no_wrap=True)
    table.add_column("KIND",       no_wrap=True)
    table.add_column("IO",         no_wrap=True)
    table.add_column("SIGNATURE",  no_wrap=True)
    table.add_column("ALLOWED",    justify="center", no_wrap=True)
    table.add_column("NAF",        justify="center", no_wrap=True)
    table.add_column("VALUES",     no_wrap=False, max_width=28)
    table.add_column("MEANING",    no_wrap=False, max_width=42)

    for row in rows:
        (
            name, arity, pred, signature, io, kind,
            meaning_pl, head, body, neg,
            allowed_values, _naf_list
        ) = row

        kind_txt  = Text(kind,  style=KIND_STYLE.get(kind, ""))
        io_txt    = Text(io,    style=IO_STYLE.get(io, ""))
        sig_txt   = ", ".join(signature) if signature else ""
        naf_txt   = Text("NAF", style="red bold") if pred in naf_set else Text("-", style="dim")
        flags_txt = _allowed_flags(head, body, neg)
        vals_txt  = ", ".join(allowed_values) if allowed_values else ""
        mean_txt  = meaning_pl or ""

        table.add_row(
            pred,
            kind_txt,
            io_txt,
            sig_txt,
            flags_txt,
            naf_txt,
            vals_txt,
            mean_txt,
        )

    total = len(rows)
    console.print()
    console.print(table)
    console.print(
        f"  [dim]{total} predykat{'y' if 2 <= total % 10 <= 4 and total % 100 not in range(11,15) else 'ów' if total != 1 else ''}[/dim]\n"
    )


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "predicates",
        help="Listuje predykaty z bazy danych.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Listuje predykaty zarejestrowane w bazie ProveNuance2.

Kolumny:
  PRED     – identyfikator name/arity
  KIND     – rola (domain/condition/decision/ui/audit/builtin)
  IO       – kierunek (input/derived/both)
  SIGNATURE – typy argumentów
  NAF      – ✓ jeśli predykat jest na liście NAF closed-world
  ALLOWED  – gdzie może wystąpić: H=head, B=body, !B=negated body
  VALUES   – dopuszczalne wartości enum (jeśli zdefiniowane)
  MEANING  – opis po polsku
        """,
    )
    p.add_argument(
        "--kind", "-k",
        nargs="+",
        metavar="KIND",
        choices=["domain", "condition", "decision", "ui", "audit", "builtin"],
        help="Filtruj po kind (można podać kilka).",
    )
    p.add_argument(
        "--io", "-i",
        nargs="+",
        metavar="IO",
        choices=["input", "derived", "both"],
        help="Filtruj po io (można podać kilka).",
    )
    p.add_argument(
        "--search", "-s",
        metavar="TEKST",
        help="Szukaj w nazwie lub opisie (ILIKE).",
    )
    p.set_defaults(func=run)
