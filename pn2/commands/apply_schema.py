"""Komenda: pn2 apply-schema — aplikuje db/schema.sql do bazy danych."""

from __future__ import annotations

import argparse
import pathlib

from rich.console import Console

from pn2._db import get_connection

console = Console()

ROOT        = pathlib.Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def run(args: argparse.Namespace) -> None:
    if not SCHEMA_PATH.exists():
        console.print(f"[red]Brak pliku schematu:[/red] {SCHEMA_PATH}")
        raise SystemExit(1)

    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    with conn, conn.cursor() as cur:
        cur.execute(sql)

    conn.commit()
    conn.close()
    console.print(f"[green]Schemat zastosowany:[/green] {SCHEMA_PATH}")
    console.print("[dim]Gotowe.[/dim]")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "apply-schema",
        help="Aplikuje db/schema.sql do bazy danych (idempotentne).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Wykonuje plik db/schema.sql przeciwko skonfigurowanej bazie PostgreSQL.

Wszystkie instrukcje używają IF NOT EXISTS — bezpieczne do wielokrotnego uruchomienia.
Służy do tworzenia nowych tabel po aktualizacji schematu.

Przykład:
  pn2 apply-schema
        """,
    )
    p.set_defaults(func=run)
