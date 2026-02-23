"""
llm_query/prompt.py — budowanie promptu dla ekstraktora reguł Horn.

Funkcje publiczne:
  fetch_predicates(domain)           -> list[str]
  fetch_constants(domain)            -> list[str]
  read_conditions(path | None)       -> str
  read_fragment(path | None)         -> str
  build_prompt(domain, conditions, fragment, template_path) -> str
"""

from __future__ import annotations

import json
import pathlib
import sys

from pn2._db import get_connection

ROOT          = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "_initial data" / "prompt-extractor.md"

_EMPTY_CONDITIONS = "{}"
_EMPTY_FRAGMENT   = "[WKLEJ TU FRAGMENT]"


def fetch_predicates(domain: str) -> list[str]:
    """
    Zwraca listę pred (name/arity) dla danej domeny.
    Zawsze dołączane: predykaty domain='generic' (w tym builtin).
    Dodatkowo: predykaty domain=<domain> (jeśli różny od 'generic').
    """
    conn = get_connection()
    with conn, conn.cursor() as cur:
        if domain == "generic":
            cur.execute(
                "SELECT pred FROM predicate WHERE domain = 'generic' ORDER BY kind, name"
            )
        else:
            cur.execute(
                """
                SELECT pred FROM predicate
                WHERE domain = 'generic' OR domain = %s
                ORDER BY kind, name
                """,
                (domain,),
            )
        return [row[0] for row in cur.fetchall()]


def fetch_constants(domain: str) -> list[str]:
    """
    Zwraca listę znanych stałych dla danej domeny.
    Zawsze dołączane: stałe domain='generic'.
    Dodatkowo: stałe domain=<domain> (jeśli różny od 'generic').
    """
    conn = get_connection()
    with conn, conn.cursor() as cur:
        if domain == "generic":
            cur.execute(
                "SELECT value FROM constant WHERE domain = 'generic' ORDER BY value"
            )
        else:
            cur.execute(
                """
                SELECT value FROM constant
                WHERE domain = 'generic' OR domain = %s
                ORDER BY value
                """,
                (domain,),
            )
        return [row[0] for row in cur.fetchall()]


def read_conditions(path: str | None) -> str:
    """Wczytuje słownik warunków z pliku JSON lub zwraca pusty obiekt."""
    if path is None:
        return _EMPTY_CONDITIONS
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[warn] Plik warunków nie istnieje: {p}", file=sys.stderr)
        return _EMPTY_CONDITIONS
    return p.read_text(encoding="utf-8").strip()


def read_fragment(path: str | None) -> str:
    """Wczytuje fragment regulaminu z pliku tekstowego lub zwraca placeholder."""
    if path is None:
        return _EMPTY_FRAGMENT
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[warn] Plik fragmentu nie istnieje: {p}", file=sys.stderr)
        return _EMPTY_FRAGMENT
    return p.read_text(encoding="utf-8").strip()


def _load_template(template_path: pathlib.Path) -> str:
    """Wczytuje szablon i usuwa otoczkę ```text / ```."""
    body = template_path.read_text(encoding="utf-8").strip()
    if body.startswith("```text"):
        body = body[len("```text"):].lstrip("\n")
    if body.endswith("```"):
        body = body[: body.rfind("```")].rstrip()
    return body


def build_prompt(
    domain: str,
    conditions: str,
    fragment: str,
    template_path: pathlib.Path = TEMPLATE_PATH,
) -> str:
    """
    Buduje gotowy prompt zastępując wszystkie placeholdery.

    Args:
        domain:        Nazwa domeny (generic / e-commerce / event).
        conditions:    Zawartość słownika warunków jako string JSON.
        fragment:      Tekst fragmentu regulaminu.
        template_path: Ścieżka do szablonu prompt-extractor.md.

    Returns:
        Wypełniony prompt gotowy do wysłania do modelu.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Brak pliku szablonu: {template_path}")

    predicates      = fetch_predicates(domain)
    allowed_json    = json.dumps(predicates, ensure_ascii=False, indent=2)
    constants       = fetch_constants(domain)
    constants_json  = json.dumps(constants, ensure_ascii=False, indent=2)
    body            = _load_template(template_path)

    return (
        body
        .replace("{{DOMAIN}}",               domain)
        .replace("{{ALLOWED_PREDICATES}}",    allowed_json)
        .replace("{{KNOWN_CONSTANTS}}",       constants_json)
        .replace("{{CONDITION_DICTIONARY}}", conditions)
        .replace("{{FRAGMENT}}",              fragment)
    )
