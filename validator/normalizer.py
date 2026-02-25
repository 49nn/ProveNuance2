"""
validator/normalizer.py — normalizacja reguły przed walidacją.

normalize_rule():
  - Zwraca głęboką kopię reguły z wypełnionymi polami domyślnymi.
  - Nie zmienia treści merytorycznej (np. quote jest tylko trimowane).
  - Ustawia negated=False dla atomów bez tego pola.
  - Ustawia constraints=[] i assumptions=[] jeśli brak.
"""

from __future__ import annotations

import copy
from typing import Any


def normalize_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Zwraca głęboką kopię reguły z wypełnionymi wartościami domyślnymi.

    Zmiany:
      - head.negated       → domyślnie False
      - body[i].negated    → domyślnie False
      - constraints        → domyślnie []
      - assumptions        → domyślnie []
      - provenance.quote   → strip() (bez zmiany treści)
    """
    rule = copy.deepcopy(rule)

    if isinstance(rule.get("head"), dict):
        rule["head"] = _normalize_atom(rule["head"])

    body = rule.get("body")
    if isinstance(body, list):
        rule["body"] = [
            _normalize_atom(a) if isinstance(a, dict) else a
            for a in body
        ]

    rule.setdefault("constraints", [])
    rule.setdefault("assumptions", [])

    prov = rule.get("provenance")
    if isinstance(prov, dict):
        q = prov.get("quote", "")
        if isinstance(q, str):
            prov["quote"] = q.strip()

    return rule


def _normalize_atom(atom: dict[str, Any]) -> dict[str, Any]:
    atom = dict(atom)
    atom.setdefault("negated", False)
    return atom
