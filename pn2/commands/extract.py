"""Komenda: pn2 extract — buduje prompt i wysyła do Gemini API."""

from __future__ import annotations

import argparse
import pathlib
import sys

from llm_query import build_prompt, read_conditions, read_fragment, call_gemini, DEFAULT_MODEL


def run(args: argparse.Namespace) -> None:
    conditions = read_conditions(args.conditions)
    fragment   = read_fragment(args.fragment)

    try:
        prompt = build_prompt(args.domain, conditions, fragment)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"Błąd budowania promptu: {e}", file=sys.stderr)
        raise SystemExit(1)

    if args.show_prompt:
        print("=== PROMPT ===")
        print(prompt)
        print("=== KONIEC PROMPTU ===\n")

    print(f"Wysyłam do Gemini ({args.model})...", file=sys.stderr)

    try:
        result = call_gemini(prompt, model=args.model)
    except ValueError as e:
        print(f"Błąd konfiguracji: {e}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"Błąd Gemini API: {e}", file=sys.stderr)
        raise SystemExit(1)

    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.write_text(result, encoding="utf-8")
        print(f"Wynik zapisany do: {out_path}", file=sys.stderr)
    else:
        print(result)


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "extract",
        help="Wysyła fragment regulaminu do Gemini i zwraca reguły Horn (JSON).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Buduje prompt (jak pn2 prompt) i wysyła go do Gemini API.
Wynik (JSON z regułami Horn) trafia na stdout lub do pliku.

Wymaga zmiennej środowiskowej GEMINI_API_KEY (lub pliku .env).

Przykłady:
  pn2 extract --domain event --fragment art18.txt
  pn2 extract --domain event --fragment art18.txt --out rules.json
  pn2 extract --domain event --fragment art18.txt --show-prompt
  pn2 extract --domain event --fragment art18.txt --model gemini-2.5-pro
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
        required=True,
        help="Plik tekstowy z fragmentem regulaminu.",
    )
    p.add_argument(
        "--conditions", "-c",
        metavar="PLIK",
        help="Plik JSON ze słownikiem warunków (domyślnie: pusty obiekt {}).",
    )
    p.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        metavar="MODEL",
        help=f"Model Gemini (domyślnie: {DEFAULT_MODEL}).",
    )
    p.add_argument(
        "--show-prompt",
        action="store_true",
        help="Wypisz prompt przed wysłaniem (do weryfikacji).",
    )
    p.add_argument(
        "--out", "-o",
        metavar="PLIK",
        help="Zapisz wynik JSON do pliku (domyślnie: stdout).",
    )
    p.set_defaults(func=run)
