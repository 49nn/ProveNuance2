"""
llm_query/constants.py — odkrywanie i utrwalanie stałych z wyników ekstraktora.

Dwa źródła w wyniku extract:
  1. args w regułach bez prefiksu "?" → klasyczne stałe ("confirmed", "auction")
  2. derived_predicates z arity=0    → propozycje/flagi ("is_eligible/0");
     pole "meaning" z odpowiedzi modelu zapisywane jako meaning_pl.

Publiczne API:
  collect_constants(result)                          -> dict[str, str | None]
  upsert_constants(conn, constants, domain)          -> int
"""

from __future__ import annotations

import re

_ARITY_0_RE = re.compile(r"^([a-z][a-z0-9_]*)/0$")

_SKIP_PREFIXES = ("?",)


def collect_constants(result: dict) -> dict[str, str | None]:
    """
    Zbiera stałe (ground terms) z wyników ekstraktora.

    Źródło 1: args w head i body reguł bez prefiksu "?" → meaning_pl = None
    Źródło 2: derived_predicates gdzie pred ma postać "name/0"
              → meaning_pl z pola "meaning" (jeśli obecne)

    Args:
        result: słownik JSON z odpowiedzi modelu

    Returns:
        Słownik {value: meaning_pl | None}.
        Jeśli ta sama stała pojawia się w obu źródłach,
        meaning z derived_predicates ma pierwszeństwo.
    """
    constants: dict[str, str | None] = {}

    # Źródło 1: args w regułach (bez znaczenia)
    for rule in result.get("rules", []):
        _collect_from_atom(rule.get("head", {}), constants)
        for atom in rule.get("body", []):
            _collect_from_atom(atom, constants)

    # Źródło 2: derived_predicates z arity=0 (z opcjonalnym znaczeniem)
    for dp in result.get("derived_predicates", []):
        pred = dp.get("pred", "")
        m = _ARITY_0_RE.match(pred)
        if m:
            value   = m.group(1)
            meaning = dp.get("meaning") or None
            # meaning ma pierwszeństwo nad None z źródła 1
            if value not in constants or meaning is not None:
                constants[value] = meaning

    return constants


def _collect_from_atom(atom: dict, out: dict[str, str | None]) -> None:
    for arg in atom.get("args", []):
        if not isinstance(arg, str):
            continue
        if arg.startswith(_SKIP_PREFIXES):
            continue
        if arg not in out:
            out[arg] = None


def upsert_constants(conn, constants: dict[str, str | None], domain: str) -> int:
    """
    Wstawia stałe do tabeli constant.

    Logika konfliktu:
      - Nowy wiersz: wstawia value, meaning_pl, domain.
      - Istniejący wiersz: uzupełnia meaning_pl tylko jeśli dotychczas był NULL
        (COALESCE — nie nadpisuje ręcznie uzupełnionych opisów).

    Args:
        conn:      połączenie psycopg2 (otwarte, bez auto-commit)
        constants: słownik {value: meaning_pl | None}
        domain:    domena przypisana nowym stałym

    Returns:
        Liczba faktycznie wstawionych nowych wierszy.
    """
    if not constants:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for value, meaning in sorted(constants.items()):
            cur.execute(
                """
                INSERT INTO constant (value, meaning_pl, domain)
                VALUES (%s, %s, %s)
                ON CONFLICT (value) DO UPDATE
                    SET meaning_pl = COALESCE(constant.meaning_pl, EXCLUDED.meaning_pl)
                """,
                (value, meaning, domain),
            )
            inserted += cur.rowcount

    return inserted
