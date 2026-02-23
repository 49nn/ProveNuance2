#!/usr/bin/env python3
"""
Inicjalizacja tabel predykatów w PostgreSQL.

Wykonuje:
  1. Tworzy schemat (schema.sql) — idempotentny
  2. Wstawia / aktualizuje manifest_policy
  3. Wstawia / aktualizuje wszystkie predykaty z predykaty-manifest.json

Użycie:
  python db/seed_predicates.py

Zmienne środowiskowe (opcjonalne, domyślne = docker-compose):
  PGHOST      localhost
  PGPORT      5433
  PGDATABASE  provenuance2
  PGUSER      provenuance2
  PGPASSWORD  provenuance2
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Brakuje psycopg2. Zainstaluj: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Ścieżki
# ---------------------------------------------------------------------------

ROOT          = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "_initial data" / "predykaty-manifest.json"
SCHEMA_PATH   = pathlib.Path(__file__).resolve().parent / "schema.sql"

# ---------------------------------------------------------------------------
# Połączenie
# ---------------------------------------------------------------------------

DSN = dict(
    host     = os.getenv("PGHOST",     "localhost"),
    port     = int(os.getenv("PGPORT", "5433")),
    dbname   = os.getenv("PGDATABASE", "provenuance2"),
    user     = os.getenv("PGUSER",     "provenuance2"),
    password = os.getenv("PGPASSWORD", "provenuance2"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bool(val: object, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    return default


def build_predicate_row(p: dict) -> tuple:
    """Konwertuje słownik predykatu z JSON na krotkę do INSERT."""
    allowed = p.get("allowed_in", {})
    vd      = p.get("value_domain")
    return (
        p["name"],
        p["arity"],
        p.get("pred") or f"{p['name']}/{p['arity']}",
        p["signature"],                          # list[str] → text[]
        p["io"],
        p["kind"],
        p.get("meaning_pl"),
        p.get("domain", "generic"),
        _bool(allowed.get("head"),         True),
        _bool(allowed.get("body"),         True),
        _bool(allowed.get("negated_body"), False),
        vd["enum_arg_index"]   if vd else None,
        vd["allowed_values"]   if vd else None,  # list[str] → text[]
        p.get("notes"),
    )


# ---------------------------------------------------------------------------
# Główna procedura
# ---------------------------------------------------------------------------

def run() -> None:
    # --- wczytaj manifest ---
    if not MANIFEST_PATH.exists():
        print(f"Nie znaleziono manifestu: {MANIFEST_PATH}", file=sys.stderr)
        sys.exit(1)

    manifest  = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    predicates = manifest.get("predicates", [])
    policy     = manifest.get("policy", {})

    print(f"Manifest: {len(predicates)} predykatów")
    print(f"Baza:     {DSN['user']}@{DSN['host']}:{DSN['port']}/{DSN['dbname']}")

    with psycopg2.connect(**DSN) as conn:
        with conn.cursor() as cur:

            # 1. Schemat
            print("Applying schema...", end=" ")
            cur.execute(schema_sql)
            print("OK")

            # 2. Polityka manifestu
            print("Upserting manifest_policy...", end=" ")
            cur.execute(
                """
                INSERT INTO manifest_policy
                    (id, whitelist_mode, naf_closed_world_predicates)
                VALUES
                    (1, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    whitelist_mode              = EXCLUDED.whitelist_mode,
                    naf_closed_world_predicates = EXCLUDED.naf_closed_world_predicates
                """,
                (
                    policy.get("whitelist_mode", "allow_only_listed"),
                    policy.get("naf_closed_world_predicates", []),
                ),
            )
            print("OK")

            # 3. Predykaty
            print(f"Upserting {len(predicates)} predicates...", end=" ")
            rows = [build_predicate_row(p) for p in predicates]

            execute_values(
                cur,
                """
                INSERT INTO predicate (
                    name, arity, pred, signature, io, kind, meaning_pl, domain,
                    allowed_in_head, allowed_in_body, allowed_in_negated_body,
                    value_domain_enum_arg_index, value_domain_allowed_values,
                    notes
                ) VALUES %s
                ON CONFLICT (name) DO UPDATE SET
                    arity                       = EXCLUDED.arity,
                    pred                        = EXCLUDED.pred,
                    signature                   = EXCLUDED.signature,
                    io                          = EXCLUDED.io,
                    kind                        = EXCLUDED.kind,
                    meaning_pl                  = EXCLUDED.meaning_pl,
                    domain                      = EXCLUDED.domain,
                    allowed_in_head             = EXCLUDED.allowed_in_head,
                    allowed_in_body             = EXCLUDED.allowed_in_body,
                    allowed_in_negated_body     = EXCLUDED.allowed_in_negated_body,
                    value_domain_enum_arg_index = EXCLUDED.value_domain_enum_arg_index,
                    value_domain_allowed_values = EXCLUDED.value_domain_allowed_values,
                    notes                       = EXCLUDED.notes
                """,
                rows,
            )
            print("OK")

        conn.commit()

    # 4. Weryfikacja
    with psycopg2.connect(**DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT io, COUNT(*) FROM predicate GROUP BY io ORDER BY io")
            counts = cur.fetchall()
            cur.execute("SELECT whitelist_mode, array_length(naf_closed_world_predicates,1) FROM manifest_policy")
            policy_row = cur.fetchone()

    print("\n--- Weryfikacja ---")
    print(f"{'io':<10} count")
    for io_val, cnt in counts:
        print(f"  {io_val:<8} {cnt}")
    print(f"\npolicy.whitelist_mode              = {policy_row[0]}")
    print(f"policy.naf_closed_world_predicates = {policy_row[1]} predykatow")
    print("\nGotowe.")


if __name__ == "__main__":
    run()
