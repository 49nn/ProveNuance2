"""Komenda: pn2 reset — usuwanie danych z bazy ProveNuance2."""

from __future__ import annotations

import argparse

from rich.console import Console

from pn2._db import get_connection

console = Console()


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

def _table_exists(cur, table: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return cur.fetchone() is not None


def _deleted(n: int, table: str) -> None:
    console.print(f"[green]Usunięto {n} wierszy z [bold]{table}[/bold][/green]")


def _skipped(table: str) -> None:
    console.print(f"[yellow]Tabela [bold]{table}[/bold] nie istnieje — pominięto.[/yellow]")


# ---------------------------------------------------------------------------
# Akcje per cel
# ---------------------------------------------------------------------------

def _reset_doc(cur, doc_id: str | None) -> None:
    if not _table_exists(cur, "document_span"):
        _skipped("document_span")
        return
    if doc_id:
        cur.execute("DELETE FROM document_span WHERE doc_id = %s", (doc_id,))
        console.print(
            f"[green]Usunięto {cur.rowcount} wierszy z [bold]document_span[/bold]"
            f" (doc_id=[cyan]{doc_id}[/cyan])[/green]"
        )
    else:
        cur.execute("DELETE FROM document_span")
        _deleted(cur.rowcount, "document_span")


def _reset_predicates(cur) -> None:
    if _table_exists(cur, "predicate"):
        cur.execute("TRUNCATE predicate RESTART IDENTITY CASCADE")
        console.print("[green]Wyczyszczono tabelę [bold]predicate[/bold] (TRUNCATE)[/green]")
    else:
        _skipped("predicate")

    if _table_exists(cur, "manifest_policy"):
        cur.execute("DELETE FROM manifest_policy")
        _deleted(cur.rowcount, "manifest_policy")
    else:
        _skipped("manifest_policy")


def _reset_rules(cur) -> None:
    if _table_exists(cur, "rule"):
        cur.execute("DELETE FROM rule")
        _deleted(cur.rowcount, "rule")
    else:
        _skipped("rule")


def _reset_conditions(cur) -> None:
    if _table_exists(cur, "condition"):
        cur.execute("DELETE FROM condition")
        _deleted(cur.rowcount, "condition")
    else:
        _skipped("condition")


def _reset_constants(cur) -> None:
    if _table_exists(cur, "constant"):
        cur.execute("DELETE FROM constant")
        _deleted(cur.rowcount, "constant")
    else:
        _skipped("constant")


def _reset_assumptions(cur) -> None:
    if _table_exists(cur, "assumption"):
        cur.execute("DELETE FROM assumption")
        _deleted(cur.rowcount, "assumption")
    else:
        _skipped("assumption")


def _reset_derived_predicates(cur) -> None:
    if _table_exists(cur, "derived_predicate"):
        cur.execute("DELETE FROM derived_predicate")
        _deleted(cur.rowcount, "derived_predicate")
    else:
        _skipped("derived_predicate")


# ---------------------------------------------------------------------------
# Główna logika
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    cel: str = args.cel
    doc_id: str | None = getattr(args, "doc_id", None)

    if doc_id and cel not in ("doc", "all"):
        console.print(
            f"[yellow]--doc-id ignorowane przy celu [bold]{cel}[/bold][/yellow]"
        )

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    with conn, conn.cursor() as cur:
        if cel == "doc":
            _reset_doc(cur, doc_id)
        elif cel == "predicates":
            _reset_predicates(cur)
        elif cel == "rules":
            _reset_rules(cur)
        elif cel == "conditions":
            _reset_conditions(cur)
        elif cel == "constants":
            _reset_constants(cur)
        elif cel == "assumptions":
            _reset_assumptions(cur)
        elif cel == "derived-predicates":
            _reset_derived_predicates(cur)
        elif cel == "all":
            _reset_doc(cur, doc_id)
            _reset_predicates(cur)
            _reset_derived_predicates(cur)
            _reset_rules(cur)
            _reset_conditions(cur)
            _reset_constants(cur)
            _reset_assumptions(cur)

    console.print("[dim]Gotowe.[/dim]")


# ---------------------------------------------------------------------------
# Rejestracja parsera
# ---------------------------------------------------------------------------

def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "reset",
        help="Usuwa dane z bazy (bez potwierdzenia).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Usuwa dane z bazy ProveNuance2. Działa natychmiast, bez pytania o potwierdzenie.

Cele:
  doc                  Usuwa spany dokumentów (document_span).
                       Opcja --doc-id ogranicza usuwanie do jednego dokumentu.
  predicates           Czyści predykaty i manifest_policy.
  derived-predicates   Czyści predykaty pochodne (derived_predicate).
  rules                Czyści reguły (gdy tabela istnieje).
  conditions           Czyści warunki (gdy tabela istnieje).
  constants            Czyści stałe domenowe (gdy tabela istnieje).
  assumptions          Czyści założenia scoped (gdy tabela istnieje).
  all                  Wykonuje wszystkie powyższe.

Przykłady:
  pn2 reset doc
  pn2 reset doc --doc-id Regulamin
  pn2 reset predicates
  pn2 reset derived-predicates
  pn2 reset all
  pn2 reset all --doc-id Regulamin
        """,
    )
    p.add_argument(
        "cel",
        metavar="CEL",
        choices=["doc", "predicates", "derived-predicates", "rules", "conditions", "constants", "assumptions", "all"],
        help="Co usunąć: doc | predicates | derived-predicates | rules | conditions | constants | assumptions | all",
    )
    p.add_argument(
        "--doc-id",
        metavar="ID",
        default=None,
        help="(tylko dla 'doc' / 'all') Ogranicz usuwanie do doc_id=ID.",
    )
    p.set_defaults(func=run)
