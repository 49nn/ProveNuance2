"""Komenda: pn2 extract — buduje prompt i wysyła do Gemini API."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from llm_query import (
    build_prompt,
    read_conditions,
    read_fragment,
    call_gemini,
    collect_constants,
    upsert_constants,
    collect_assumptions,
    upsert_assumptions,
    collect_rules,
    upsert_rules,
    collect_conditions,
    upsert_conditions,
    DEFAULT_MODEL,
)
from pn2._db import get_connection


def _parse_result(raw: str) -> dict | None:
    """Próbuje sparsować JSON z odpowiedzi modelu (odrzuca otoczkę ```json```)."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _save(label: str, items, upsert_fn, conn_factory, domain: str) -> None:
    """Pomocnicza: upsert z logowaniem błędów."""
    if not items:
        print(f"Brak {label} do zapisania.", file=sys.stderr)
        return
    try:
        conn = conn_factory()
        n = upsert_fn(conn, items, domain)
        conn.commit()
        conn.close()
        print(f"Zapisano {n} {label} (domena: {domain}).", file=sys.stderr)
    except Exception as e:
        print(f"[warn] Błąd zapisu {label} do bazy: {e}", file=sys.stderr)


def run(args: argparse.Namespace) -> None:
    conditions_txt = read_conditions(args.conditions)
    fragment       = read_fragment(args.fragment)

    try:
        prompt = build_prompt(args.domain, conditions_txt, fragment)
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
        raw = call_gemini(prompt, model=args.model)
    except ValueError as e:
        print(f"Błąd konfiguracji: {e}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"Błąd Gemini API: {e}", file=sys.stderr)
        raise SystemExit(1)

    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.write_text(raw, encoding="utf-8")
        print(f"Wynik zapisany do: {out_path}", file=sys.stderr)
    else:
        print(raw)

    result = _parse_result(raw)
    if result is None:
        print("[warn] Nie można sparsować JSON — dane nie zostały zapisane.", file=sys.stderr)
        return

    domain = args.domain

    # --- reguły ---
    rules = collect_rules(result)
    print(f"  reguły ({len(rules)}): {', '.join(r['rule_id'] for r in rules)}", file=sys.stderr)
    _save("reguł", rules, upsert_rules, get_connection, domain)

    # --- warunki ---
    conds = collect_conditions(result)
    if conds:
        print(f"  warunki ({len(conds)}): {', '.join(c['id'] for c in conds)}", file=sys.stderr)
    _save("warunków", conds, upsert_conditions, get_connection, domain)

    # --- stałe ---
    constants = collect_constants(result)
    if constants:
        from llm_query.constants import _ARITY_0_RE
        arity0 = {
            v for v in constants
            if any(
                _ARITY_0_RE.match(dp.get("pred", "")) and dp["pred"].startswith(v + "/")
                for dp in result.get("derived_predicates", [])
            )
        }
        plain = set(constants) - arity0
        if plain:
            print(f"  args-stałe ({len(plain)}): {', '.join(sorted(plain))}", file=sys.stderr)
        if arity0:
            with_meaning = {v for v in arity0 if constants[v]}
            print(
                f"  arity-0 pred ({len(arity0)}): {', '.join(sorted(arity0))}"
                + (f" [{len(with_meaning)} z opisem]" if with_meaning else ""),
                file=sys.stderr,
            )
    _save("stałych", constants, upsert_constants, get_connection, domain)

    # --- założenia ---
    assumptions = collect_assumptions(result)
    if assumptions:
        by_type: dict[str, int] = {}
        for a in assumptions:
            by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        summary = ", ".join(f"{t}={n}" for t, n in sorted(by_type.items()))
        print(f"  założenia ({len(assumptions)}): {summary}", file=sys.stderr)
    _save("założeń", assumptions, upsert_assumptions, get_connection, domain)


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "extract",
        help="Wysyła fragment regulaminu do Gemini i zwraca reguły Horn (JSON).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""
Buduje prompt (jak pn2 prompt) i wysyła go do Gemini API.
Wynik (JSON z regułami Horn) trafia na stdout lub do pliku.
Po ekstrakcji automatycznie zapisuje do bazy:
  - reguły Horn       → tabela rule
  - warunki nazwane   → tabela condition
  - stałe domenowe    → tabela constant
  - założenia scoped  → tabela assumption

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
