"""
llm_query/assumptions.py — odkrywanie i utrwalanie założeń (ScopedAssumptions).

Założenia zbierane są z dwóch miejsc w wynikach ekstraktora:
  1. rules[*].assumptions          (source_type='rule',      source_id=rule.id)
  2. new_conditions[*].assumptions (source_type='condition', source_id=condition.id)

Publiczne API:
  collect_assumptions(result)                    -> list[dict]
  upsert_assumptions(conn, assumptions, domain)  -> int
"""

from __future__ import annotations

_VALID_TYPES = frozenset({
    "data_contract",
    "data_semantics",
    "enumeration",
    "closed_world",
    "external_computation",
    "conflict_resolution",
    "missing_predicate",
})


def collect_assumptions(result: dict) -> list[dict]:
    """
    Zbiera założenia (ScopedAssumption) z wyników ekstraktora.

    Args:
        result: słownik JSON z odpowiedzi modelu

    Returns:
        Lista płaskich słowników gotowych do wstawienia do tabeli assumption.
        Każdy słownik ma klucze:
          fragment_id, source_type, source_id,
          about_pred, about_atom_index, about_arg_index, about_const,
          type, text
    """
    fragment_id = result.get("fragment_id") or "unknown"
    items: list[dict] = []

    for rule in result.get("rules", []):
        source_id = rule.get("id") or "?"
        for a in rule.get("assumptions", []):
            item = _flatten(fragment_id, "rule", source_id, a)
            if item:
                items.append(item)

    for cond in result.get("new_conditions", []):
        source_id = cond.get("id") or "?"
        for a in cond.get("assumptions", []):
            item = _flatten(fragment_id, "condition", source_id, a)
            if item:
                items.append(item)

    return items


def _flatten(
    fragment_id: str,
    source_type: str,
    source_id: str,
    a: dict,
) -> dict | None:
    atype = a.get("type", "")
    text  = (a.get("text") or "").strip()
    if not atype or not text:
        return None
    if atype not in _VALID_TYPES:
        return None

    about = a.get("about") or {}
    return {
        "fragment_id":      fragment_id,
        "source_type":      source_type,
        "source_id":        source_id,
        "about_pred":       about.get("pred") or "",
        "about_atom_index": about.get("atom_index"),
        "about_arg_index":  about.get("arg_index"),
        "about_const":      about.get("const"),
        "type":             atype,
        "text":             text,
    }


def upsert_assumptions(conn, assumptions: list[dict], domain: str) -> int:
    """
    Wstawia założenia do tabeli assumption.

    Logika konfliktu (UNIQUE na fragment_id, source_type, source_id, about_pred, type):
      - Nowy wiersz: wstawia wszystkie pola.
      - Istniejący wiersz: nadpisuje text, about_atom_index, about_arg_index, about_const
        (re-ekstrakcja tego samego fragmentu aktualizuje treść założenia).

    Args:
        conn:        połączenie psycopg2 (otwarte, bez auto-commit)
        assumptions: lista słowników z collect_assumptions()
        domain:      domena przypisana nowym wierszom

    Returns:
        Liczba faktycznie wstawionych lub zaktualizowanych wierszy.
    """
    if not assumptions:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for a in assumptions:
            cur.execute(
                """
                INSERT INTO assumption (
                    fragment_id, source_type, source_id,
                    about_pred, about_atom_index, about_arg_index, about_const,
                    type, text, domain
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fragment_id, source_type, source_id, about_pred, type)
                DO UPDATE SET
                    text             = EXCLUDED.text,
                    about_atom_index = EXCLUDED.about_atom_index,
                    about_arg_index  = EXCLUDED.about_arg_index,
                    about_const      = EXCLUDED.about_const
                """,
                (
                    a["fragment_id"], a["source_type"], a["source_id"],
                    a["about_pred"], a["about_atom_index"], a["about_arg_index"],
                    a["about_const"], a["type"], a["text"], domain,
                ),
            )
            inserted += cur.rowcount

    return inserted
