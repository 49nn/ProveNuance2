"""
llm_query/derived_rules.py — utrwalanie reguł Horn odkrytych przez ekstraktor LLM.

Reguły generowane przez model trafiają do tabeli derived_rule (oddzielona od
tabeli rule, która zawiera wzorcowe reguły z manifestu).

Publiczne API:
  upsert_derived_rules(conn, rules, domain)  -> int
"""

from __future__ import annotations


def upsert_derived_rules(conn, rules: list[dict], domain: str) -> int:
    """
    Wstawia reguły Horn do tabeli derived_rule.

    Ta sama logika UPSERT co upsert_rules, lecz dla tabeli derived_rule
    — przeznaczonej wyłącznie na reguły odkryte automatycznie przez ekstraktor.

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
                INSERT INTO derived_rule (
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
