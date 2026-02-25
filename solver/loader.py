"""
solver/loader.py — ładowanie reguł i warunków z bazy, faktów z JSON.

Publiczne API:
  load_facts_json(path)                          -> (case_id, domain, Facts)
  load_rules_from_db(conn, domain, fragment_id)  -> list[Rule]
  load_conditions_from_db(conn)                  -> dict[str, list[Atom]]
  parse_goal(goal_str)                           -> (pred, args_tuple)
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Optional

from .types import Atom, Rule

Facts = dict[str, set[tuple[str, ...]]]


# ---------------------------------------------------------------------------
# Fakty EDB z JSON
# ---------------------------------------------------------------------------

def load_facts_json(path: pathlib.Path) -> tuple[str, str, Facts]:
    """
    Wczytuje fakty EDB z pliku JSON.

    Oczekiwany format::

        {
            "case_id": "sprawa-001",
            "domain":  "event",
            "facts": [
                {"pred": "delivery_status", "args": ["ord-1", "confirmed"]},
                {"pred": "order_amount",    "args": ["ord-1", "150"]}
            ]
        }

    Wartości liczbowe w args są konwertowane na stringi (solver pracuje na str).

    Returns:
        (case_id, domain, facts_dict)
    """
    raw    = json.loads(path.read_text(encoding="utf-8"))
    case_id = raw.get("case_id", "")
    domain  = raw.get("domain", "generic")
    facts: Facts = {}

    for f in raw.get("facts", []):
        pred = str(f["pred"])
        args = tuple(str(a) for a in f.get("args", []))
        facts.setdefault(pred, set()).add(args)

    return case_id, domain, facts


# ---------------------------------------------------------------------------
# Reguły z bazy
# ---------------------------------------------------------------------------

def _atom_from_dict(d: dict) -> Atom:
    return Atom(
        pred=str(d.get("pred", "")),
        args=tuple(str(a) for a in d.get("args", [])),
        negated=bool(d.get("negated", False)),
    )


def _load_rules_from_table(
    conn,
    table:       str,
    domain:      Optional[str] = None,
    fragment_id: Optional[str] = None,
) -> list[Rule]:
    """Ładuje reguły Horna z podanej tabeli (rule lub derived_rule)."""
    wheres: list[str] = []
    params: list      = []

    if domain:
        wheres.append("domain = %s")
        params.append(domain)
    if fragment_id:
        wheres.append("fragment_id = %s")
        params.append(fragment_id)

    where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    sql   = (
        f"SELECT rule_id, fragment_id, head_pred, head_args, body, prov_unit, prov_quote "
        f"FROM {table} {where} ORDER BY id"
    )

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    rules: list[Rule] = []
    for rule_id, frag_id, head_pred, head_args_raw, body_raw, prov_unit_raw, prov_quote_raw in rows:
        if isinstance(head_args_raw, str):
            head_args_list = json.loads(head_args_raw)
        else:
            head_args_list = head_args_raw or []

        if isinstance(body_raw, str):
            body_list = json.loads(body_raw)
        else:
            body_list = body_raw or []

        prov_unit: list[str] = list(prov_unit_raw) if prov_unit_raw else []
        prov_quote: str      = prov_quote_raw or ""

        rules.append(Rule(
            rule_id=rule_id,
            fragment_id=frag_id,
            head_pred=head_pred,
            head_args=tuple(str(a) for a in head_args_list),
            body=[_atom_from_dict(d) for d in body_list],
            prov_unit=prov_unit,
            prov_quote=prov_quote,
        ))

    return rules


def load_rules_from_db(
    conn,
    domain:      Optional[str] = None,
    fragment_id: Optional[str] = None,
) -> list[Rule]:
    """
    Ładuje reguły Horna z tabeli rule (manifest).

    Args:
        conn:        otwarte połączenie psycopg2
        domain:      opcjonalny filtr po domenie
        fragment_id: opcjonalny filtr po fragment_id

    Returns:
        Lista obiektów Rule.
    """
    return _load_rules_from_table(conn, "rule", domain, fragment_id)


def load_derived_rules_from_db(
    conn,
    domain:      Optional[str] = None,
    fragment_id: Optional[str] = None,
) -> list[Rule]:
    """
    Ładuje reguły Horna z tabeli derived_rule (odkryte automatycznie przez ekstraktor).

    Args:
        conn:        otwarte połączenie psycopg2
        domain:      opcjonalny filtr po domenie
        fragment_id: opcjonalny filtr po fragment_id

    Returns:
        Lista obiektów Rule.
    """
    return _load_rules_from_table(conn, "derived_rule", domain, fragment_id)


# ---------------------------------------------------------------------------
# Warunki z bazy
# ---------------------------------------------------------------------------

def load_conditions_from_db(conn) -> dict[str, list[Atom]]:
    """
    Ładuje definicje warunków (ConditionDefinition) z tabeli condition.
    Warunki są globalne (nie filtrujemy po domenie).

    Returns:
        Słownik condition_id → list[Atom] (required_facts).
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, required_facts FROM condition ORDER BY id")
        rows = cur.fetchall()

    conditions: dict[str, list[Atom]] = {}
    for cond_id, required_raw in rows:
        if isinstance(required_raw, str):
            req_list = json.loads(required_raw)
        else:
            req_list = required_raw or []
        conditions[cond_id] = [_atom_from_dict(d) for d in req_list]

    return conditions


# ---------------------------------------------------------------------------
# Parsowanie celu (goal)
# ---------------------------------------------------------------------------

_GOAL_RE = re.compile(r"^([a-z_][a-z0-9_]*)(?:\s*\(([^)]*)\))?\s*$", re.IGNORECASE)


def parse_goal(goal_str: str) -> tuple[str, tuple[str, ...]]:
    """
    Parsuje string celu na (pred, args).

    Przykłady::

        "auction(?O)"            → ("auction", ("?O",))
        "eligible_bidder(?P, x)" → ("eligible_bidder", ("?P", "x"))
        "is_valid"               → ("is_valid", ())

    Raises:
        ValueError jeśli format jest nieprawidłowy.
    """
    m = _GOAL_RE.match(goal_str.strip())
    if not m:
        raise ValueError(f"Nieprawidłowy format celu: '{goal_str}'")

    pred     = m.group(1)
    raw_args = m.group(2)

    if raw_args is None or raw_args.strip() == "":
        args: tuple[str, ...] = ()
    else:
        args = tuple(a.strip().strip("\"'") for a in raw_args.split(","))

    return pred, args
