"""Komenda: pn2 prompt — generuje wypełniony prompt do ekstraktora reguł."""

from __future__ import annotations

import argparse
import pathlib
import sys

from llm_query import build_prompt, read_conditions, read_fragment


def run(args: argparse.Namespace) -> None:
    conditions = read_conditions(args.conditions)
    fragment   = read_fragment(args.fragment)

    try:
        filled = build_prompt(args.domain, conditions, fragment)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"Błąd połączenia z bazą: {e}", file=sys.stderr)
        raise SystemExit(1)

    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.write_text(filled, encoding="utf-8")
        print(f"Prompt zapisany do: {out_path}")
    else:
        print(filled)


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "prompt",
        help="Generuje wypełniony prompt dla ekstraktora reguł Horn.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Wypełnia szablon prompt-extractor.md danymi z bazy i plików wejściowych.

Placeholdery:
  {{DOMAIN}}               nazwa domeny
  {{ALLOWED_PREDICATES}}   JSON lista predykatów (generic + domena)
  {{CONDITION_DICTIONARY}} zawartość pliku JSON ze słownikiem warunków
  {{FRAGMENT}}             tekst fragmentu regulaminu

Przykłady:
  pn2 prompt --domain event
  pn2 prompt --domain event --fragment span.txt --conditions cond.json
  pn2 prompt --domain e-commerce --out prompt_ecommerce.txt
        """,
    )
    p.add_argument(
        "--domain", "-d",
        default="generic",
        choices=["generic", "e-commerce", "event"],
        help="Domena predykatów (domyślnie: generic).",
    )
    p.add_argument(
        "--fragment", "-f",
        metavar="PLIK",
        help="Plik tekstowy z fragmentem regulaminu (domyślnie: placeholder).",
    )
    p.add_argument(
        "--conditions", "-c",
        metavar="PLIK",
        help="Plik JSON ze słownikiem warunków (domyślnie: pusty obiekt {}).",
    )
    p.add_argument(
        "--out", "-o",
        metavar="PLIK",
        help="Zapisz wynik do pliku (domyślnie: stdout).",
    )
    p.set_defaults(func=run)
