"""
Struktury danych dla warunków (conditions).

Mapowanie na schemat: horn_json_v2_with_scoped_assumptions
  $defs: ConditionDefinition, NewConditionDefinition
  properties: condition_dictionary
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import Atom, Provenance, ScopedAssumption

# ---------------------------------------------------------------------------
# Aliasy typów
# ---------------------------------------------------------------------------

# Wzorzec: ^[a-z][a-z0-9_]*$  np. "buyer_active"
type ConditionId = str

# Słownik warunków wejściowych: ConditionId → definicja
# Schemat: properties/condition_dictionary
type ConditionDictionary = dict[ConditionId, ConditionDefinition]


# ---------------------------------------------------------------------------
# ConditionDefinition
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ConditionDefinition:
    """
    Definicja nazwanego warunku z wymaganymi i opcjonalnymi faktami.

    Schemat: $defs/ConditionDefinition
    - id:             identyfikator warunku, wzorzec ^[a-z][a-z0-9_]*$
    - meaning_pl:     opis semantyczny po polsku
    - required_facts: atomy które MUSZĄ być spełnione
    - optional_facts: atomy które mogą, ale nie muszą być spełnione
    - provenance:     źródło w dokumencie
    - assumptions:    założenia ograniczone do tego warunku
    - notes:          dodatkowe uwagi (opcjonalnie)

    NewConditionDefinition (schemat: $defs/NewConditionDefinition) to alias:
    warunek który NIE istnieje w condition_dictionary i powinien zostać dodany.
    Rozróżnienie jest kontekstualne — ten sam typ, inna rola.
    """
    id: ConditionId
    meaning_pl: str
    required_facts: list[Atom]
    optional_facts: list[Atom]
    provenance: Provenance
    assumptions: list[ScopedAssumption]
    notes: str | None = None

    @property
    def all_facts(self) -> list[Atom]:
        """Wszystkie atomy: wymagane + opcjonalne."""
        return self.required_facts + self.optional_facts


# ---------------------------------------------------------------------------
# Pomocnicze typy kontekstowe
# ---------------------------------------------------------------------------

# Alias semantyczny: warunek nowy (spoza condition_dictionary).
# Typ identyczny z ConditionDefinition — różnica jest tylko kontekstualna.
type NewConditionDefinition = ConditionDefinition
