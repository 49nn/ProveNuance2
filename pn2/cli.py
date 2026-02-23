"""
pn2 — narzędzie CLI dla ProveNuance2.

Użycie:
  pn2 <komenda> [opcje]

Komendy:
  predicates   Listuje predykaty z bazy danych.
  ingest       Parsuje PDF na spany sekcji i zapisuje do JSON / bazy.
  reset        Usuwa dane z bazy (doc / predicates / rules / conditions / all).
  prompt       Generuje wypełniony prompt dla ekstraktora reguł Horn.
  extract      Wysyła fragment regulaminu do Gemini i zwraca reguły Horn.
  constants    Listuje stałe domenowe odkryte przez ekstraktor.
  assumptions  Listuje założenia (ScopedAssumptions) odkryte przez ekstraktor.
  rules        Listuje reguły Horna odkryte przez ekstraktor.
  conditions   Listuje warunki nazwane (ConditionDefinition) odkryte przez ekstraktor.
  load-manifest Ładuje manifest predykatów (JSON) do tabeli predicate.
  apply-schema  Aplikuje db/schema.sql do bazy danych (idempotentne).
  solve         Uruchamia solver Datalog na regułach z bazy i faktach z JSON.
  extract-document  Ekstrakcja reguł dla wszystkich spanów dokumentu (batch).
"""

from __future__ import annotations

import argparse
import sys

# Windows: terminal może używać cp1252 — wymuszamy UTF-8, żeby polskie znaki
# w tekstach pomocy argparse były wypisywane poprawnie.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from pn2.commands import predicates as cmd_predicates
from pn2.commands import ingest as cmd_ingest
from pn2.commands import reset as cmd_reset
from pn2.commands import prompt as cmd_prompt
from pn2.commands import extract as cmd_extract
from pn2.commands import constants as cmd_constants
from pn2.commands import assumptions as cmd_assumptions
from pn2.commands import rules as cmd_rules
from pn2.commands import conditions as cmd_conditions
from pn2.commands import load_manifest as cmd_load_manifest
from pn2.commands import apply_schema as cmd_apply_schema
from pn2.commands import solve as cmd_solve
from pn2.commands import extract_document as cmd_extract_document


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pn2",
        description="ProveNuance2 — narzędzie CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="pn2 0.1.0"
    )

    subparsers = parser.add_subparsers(
        title="komendy",
        metavar="<komenda>",
        dest="command",
    )
    subparsers.required = True

    cmd_predicates.add_parser(subparsers)
    cmd_ingest.add_parser(subparsers)
    cmd_reset.add_parser(subparsers)
    cmd_prompt.add_parser(subparsers)
    cmd_extract.add_parser(subparsers)
    cmd_constants.add_parser(subparsers)
    cmd_assumptions.add_parser(subparsers)
    cmd_rules.add_parser(subparsers)
    cmd_conditions.add_parser(subparsers)
    cmd_load_manifest.add_parser(subparsers)
    cmd_apply_schema.add_parser(subparsers)
    cmd_solve.add_parser(subparsers)
    cmd_extract_document.add_parser(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
