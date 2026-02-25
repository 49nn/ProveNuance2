"""Komenda: pn2 apply-schema — aplikuje db/schema.sql do bazy danych."""

from __future__ import annotations

import argparse
import pathlib

from rich.console import Console

from pn2._db import get_connection

console = Console()

ROOT        = pathlib.Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def _split_statements(sql: str) -> list[str]:
    """
    Dzieli SQL na pojedyncze instrukcje, respektując bloki $$...$$
    (dollar-quoting używane w DO $$ BEGIN ... END $$).

    Każda instrukcja kończy się średnikiem na końcu linii (poza blokami $$).
    Puste wyniki są pomijane.
    """
    stmts: list[str] = []
    buf:   list[str] = []
    in_dollar = False

    for line in sql.splitlines(keepends=True):
        buf.append(line)
        # Każde wystąpienie $$ przełącza tryb dollar-quote
        if line.count("$$") % 2 == 1:
            in_dollar = not in_dollar
        # Koniec instrukcji: linia kończy się ; i nie jesteśmy w bloku $$
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []

    remaining = "".join(buf).strip()
    if remaining:
        stmts.append(remaining)

    return stmts


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

    # autocommit=True + wykonywanie instrukcji jedna po drugiej jest wymagane,
    # bo ALTER TYPE ADD VALUE musi być zatwierdzone (własna transakcja) zanim
    # nowa wartość enuma pojawi się w CREATE TABLE w kolejnej instrukcji.
    # Cały schema.sql jest idempotentny (IF NOT EXISTS / EXCEPTION WHEN).
    conn.autocommit = True
    stmts = _split_statements(sql)
    try:
        with conn.cursor() as cur:
            for stmt in stmts:
                cur.execute(stmt)
    except Exception as e:
        console.print(f"[red]Błąd wykonania schematu:[/red] {e}")
        conn.close()
        raise SystemExit(1)

    conn.close()
    console.print(f"[green]Schemat zastosowany:[/green] {SCHEMA_PATH} ({len(stmts)} instrukcji)")
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
