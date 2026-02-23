"""
llm_query/rules.py — odkrywanie i utrwalanie reguł Horna z wyników ekstraktora.

Publiczne API:
  collect_rules(result)                    -> list[dict]
  upsert_rules(conn, rules, domain)        -> int
"""

from __future__ import annotations

import json


def collect_rules(result: dict) -> list[dict]:
    """
    Zbiera reguły Horna z wyników ekstraktora.

    Args:
        result: słownik JSON z odpowiedzi modelu

    Returns:
        Lista płaskich słowników gotowych do wstawienia do tabeli rule.
        Każdy słownik ma klucze:
          fragment_id, rule_id, head_pred, head_args (JSON str),
          body (JSON str), prov_unit, prov_quote, notes
    """
    fragment_id = result.get("fragment_id") or "unknown"
    items: list[dict] = []

    for rule in result.get("rules", []):
        item = _flatten_rule(fragment_id, rule)
        if item:
            items.append(item)

    return items


def _flatten_rule(fragment_id: str, rule: dict) -> dict | None:
    rule_id = (rule.get("id") or "").strip()
    if not rule_id:
        return None

    head = rule.get("head") or {}
    head_pred = (head.get("pred") or "").strip()
    if not head_pred:
        return None

    prov = rule.get("provenance") or {}

    return {
        "fragment_id": fragment_id,
        "rule_id":     rule_id,
        "head_pred":   head_pred,
        "head_args":   json.dumps(head.get("args") or [], ensure_ascii=False),
        "body":        json.dumps(rule.get("body") or [], ensure_ascii=False),
        "prov_unit":   prov.get("unit") or [],
        "prov_quote":  (prov.get("quote") or "")[:400],
        "notes":       rule.get("notes"),
    }


def upsert_rules(conn, rules: list[dict], domain: str) -> int:
    """
    Wstawia reguły do tabeli rule.

    Logika konfliktu (UNIQUE na fragment_id, rule_id):
      - Nowy wiersz: wstawia wszystkie pola.
      - Istniejący wiersz: nadpisuje head_pred, head_args, body, prov_unit, prov_quote, notes
        (re-ekstrakcja tego samego fragmentu aktualizuje treść reguły).

    Args:
        conn:   połączenie psycopg2 (otwarte, bez auto-commit)
        rules:  lista słowników z collect_rules()
        domain: domena przypisana nowym wierszom

    Returns:
        Liczba faktycznie wstawionych lub zaktualizowanych wierszy.
    """
    if not rules:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for r in rules:
            cur.execute(
                """
                INSERT INTO rule (
                    fragment_id, rule_id,
                    head_pred, head_args, body,
                    prov_unit, prov_quote,
                    domain, notes
                )
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
                ON CONFLICT (fragment_id, rule_id) DO UPDATE SET
                    head_pred  = EXCLUDED.head_pred,
                    head_args  = EXCLUDED.head_args,
                    body       = EXCLUDED.body,
                    prov_unit  = EXCLUDED.prov_unit,
                    prov_quote = EXCLUDED.prov_quote,
                    notes      = EXCLUDED.notes
                """,
                (
                    r["fragment_id"], r["rule_id"],
                    r["head_pred"], r["head_args"], r["body"],
                    r["prov_unit"], r["prov_quote"],
                    domain, r["notes"],
                ),
            )
            inserted += cur.rowcount

    return inserted
