"""
Struktury danych dla stałych domenowych (constants).

Stałe to wartości ground-term odkrywane przez ekstraktor reguł Horn:
  1. args w regułach bez prefiksu "?" (np. "confirmed", "auction")
  2. derived_predicates z arity=0 (np. "is_eligible/0" → value "is_eligible")
"""

from __future__ import annotations

from dataclasses import dataclass

from .predicates import DomainScope


@dataclass(slots=True)
class ConstantSpec:
    """
    Stała domenowa (ground term).

    - value:      napis będący stałą, np. "confirmed", "auction"
    - domain:     zakres domenowy (generic / e-commerce / event)
    - meaning_pl: opcjonalny opis po polsku (uzupełniany ręcznie lub przez model)
    - notes:      dodatkowe uwagi
    """
    value:      str
    domain:     DomainScope = DomainScope.GENERIC
    meaning_pl: str | None = None
    notes:      str | None = None
