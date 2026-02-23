"""
llm_query/conditions_store.py — odkrywanie i utrwalanie warunków nazwanych.

Źródło: new_conditions w wyniku ekstraktora.
Warunki mają globalnie unikalne id (stable snake_case) — używane w meets_condition/2.

Publiczne API:
  collect_conditions(result)                    -> list[dict]
  upsert_conditions(conn, conditions, domain)   -> int
"""

from __future__ import annotations

import json


def collect_conditions(result: dict) -> list[dict]:
    """
    Zbiera nowe warunki (new_conditions) z wyników ekstraktora.

    Args:
        result: słownik JSON z odpowiedzi modelu

    Returns:
        Lista płaskich słowników gotowych do wstawienia do tabeli condition.
        Każdy słownik ma klucze:
          id, meaning_pl, required_facts (JSON str), optional_facts (JSON str),
          prov_unit, prov_quote, notes
    """
    fragment_id = result.get("fragment_id") or "unknown"
    items: list[dict] = []

    for cond in result.get("new_conditions", []):
        item = _flatten_condition(fragment_id, cond)
        if item:
            items.append(item)

    return items


def _flatten_condition(fragment_id: str, cond: dict) -> dict | None:
    cond_id = (cond.get("id") or "").strip()
    meaning = (cond.get("meaning_pl") or "").strip()
    if not cond_id or not meaning:
        return None

    prov = cond.get("provenance") or {}

    return {
        "id":             cond_id,
        "meaning_pl":     meaning,
        "required_facts": json.dumps(cond.get("required_facts") or [], ensure_ascii=False),
        "optional_facts": json.dumps(cond.get("optional_facts") or [], ensure_ascii=False),
        "prov_unit":      prov.get("unit") or [],
        "prov_quote":     (prov.get("quote") or "")[:400],
        "notes":          cond.get("notes"),
    }


def upsert_conditions(conn, conditions: list[dict], domain: str) -> int:
    """
    Wstawia warunki do tabeli condition.

    Logika konfliktu (PRIMARY KEY na id):
      - Nowy wiersz: wstawia wszystkie pola.
      - Istniejący wiersz:
          * meaning_pl: uzupełniane COALESCE (nie nadpisuje ręcznych opisów)
          * required_facts, optional_facts: nadpisywane (aktualizacja definicji)
          * prov_unit, prov_quote: nadpisywane

    Args:
        conn:       połączenie psycopg2 (otwarte, bez auto-commit)
        conditions: lista słowników z collect_conditions()
        domain:     domena przypisana nowym wierszom

    Returns:
        Liczba faktycznie wstawionych lub zaktualizowanych wierszy.
    """
    if not conditions:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for c in conditions:
            cur.execute(
                """
                INSERT INTO condition (
                    id, meaning_pl,
                    required_facts, optional_facts,
                    prov_unit, prov_quote,
                    domain, notes
                )
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    meaning_pl     = COALESCE(condition.meaning_pl, EXCLUDED.meaning_pl),
                    required_facts = EXCLUDED.required_facts,
                    optional_facts = EXCLUDED.optional_facts,
                    prov_unit      = EXCLUDED.prov_unit,
                    prov_quote     = EXCLUDED.prov_quote,
                    notes          = COALESCE(condition.notes, EXCLUDED.notes)
                """,
                (
                    c["id"], c["meaning_pl"],
                    c["required_facts"], c["optional_facts"],
                    c["prov_unit"], c["prov_quote"],
                    domain, c["notes"],
                ),
            )
            inserted += cur.rowcount

    return inserted
