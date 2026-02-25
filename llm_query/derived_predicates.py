"""
llm_query/derived_predicates.py — odkrywanie i utrwalanie predykatów pochodnych.

Predykaty pochodne to głowy (head_pred) reguł Horn odkrytych przez ekstraktor.
Nie są zdefiniowane w manifeście — ich obecność odkrywana jest automatycznie.

Publiczne API:
  collect_derived_predicates(rules)                    -> list[dict]
  upsert_derived_predicates(conn, items, domain)       -> int
"""

from __future__ import annotations

import json


def collect_derived_predicates(rules: list[dict]) -> list[dict]:
    """
    Na podstawie zebranych reguł buduje wpisy do derived_predicate.

    Jeden rekord per unikalne (head_pred, arity) — jeśli ten sam predykat
    pojawia się jako głowa kilku reguł, rejestrowany jest tylko raz
    (z opisem z pierwszej napotkanej reguły).

    meaning_pl jest generowany statycznie z:
      - head_pred i arity
      - rule_id pierwszej reguły
      - fragment_id
      - prov_quote (pierwsze 120 znaków)

    Args:
        rules: lista słowników z collect_rules() — zawiera klucze:
               fragment_id, rule_id, head_pred, head_args (JSON str),
               prov_quote, notes

    Returns:
        Lista słowników gotowych do upsert_derived_predicates().
    """
    seen: dict[str, dict] = {}  # klucz: "pred/arity"

    for rule in rules:
        head_pred = (rule.get("head_pred") or "").strip()
        if not head_pred:
            continue

        head_args_raw = rule.get("head_args", "[]")
        if isinstance(head_args_raw, str):
            try:
                head_args = json.loads(head_args_raw)
            except (ValueError, TypeError):
                head_args = []
        else:
            head_args = head_args_raw or []

        arity    = len(head_args)
        pred_key = f"{head_pred}/{arity}"

        if pred_key in seen:
            continue

        fragment_id = rule.get("fragment_id") or "unknown"
        rule_id     = rule.get("rule_id") or "?"
        prov_quote  = (rule.get("prov_quote") or "")[:120].strip()

        meaning_pl = (
            f"Predykat pochodny odkryty automatycznie z reguły {rule_id}"
            f" (fragment: {fragment_id})."
        )
        if prov_quote:
            meaning_pl += f" Kontekst: {prov_quote}…"

        seen[pred_key] = {
            "name":               head_pred,
            "arity":              arity,
            "pred":               pred_key,
            "signature":          ["any"] * arity,
            "meaning_pl":         meaning_pl,
            "source_fragment_id": fragment_id,
        }

    return list(seen.values())


def upsert_derived_predicates(conn, items: list[dict], domain: str) -> int:
    """
    Wstawia predykaty pochodne do tabeli derived_predicate.

    Logika konfliktu (UNIQUE na pred):
      - Nowy wiersz: wstawia wszystkie pola (io='derived', kind='auto_discovered').
      - Istniejący wiersz: aktualizuje meaning_pl tylko gdy nowe jest niepuste
        (COALESCE); domain i source_fragment_id zawsze nadpisuje.

    Args:
        conn:   połączenie psycopg2 (otwarte, bez auto-commit)
        items:  lista słowników z collect_derived_predicates()
        domain: domena przypisana nowym wierszom

    Returns:
        Liczba wstawionych lub zaktualizowanych wierszy.
    """
    if not items:
        return 0

    inserted = 0
    with conn.cursor() as cur:
        for item in items:
            sig_arr = item["signature"]  # list[str]

            cur.execute(
                """
                INSERT INTO derived_predicate (
                    name, arity, pred, signature,
                    io, kind,
                    meaning_pl, domain, source_fragment_id
                )
                VALUES (
                    %s, %s, %s, %s,
                    'derived', 'auto_discovered',
                    %s, %s, %s
                )
                ON CONFLICT (pred) DO UPDATE SET
                    meaning_pl         = COALESCE(EXCLUDED.meaning_pl,
                                                  derived_predicate.meaning_pl),
                    domain             = EXCLUDED.domain,
                    source_fragment_id = EXCLUDED.source_fragment_id
                """,
                (
                    item["name"],
                    item["arity"],
                    item["pred"],
                    sig_arr,
                    item["meaning_pl"],
                    domain,
                    item["source_fragment_id"],
                ),
            )
            inserted += cur.rowcount

    return inserted
