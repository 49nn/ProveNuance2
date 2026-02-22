"""
Struktury danych dla reguł Horna (rules).

Mapowanie na schemat: horn_json_v2_with_scoped_assumptions
  $defs: Rule
  properties: rules
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .common import Atom, Provenance, ScopedAssumption

# ---------------------------------------------------------------------------
# Aliasy typów
# ---------------------------------------------------------------------------

# Wzorzec: ^[A-Za-z][A-Za-z0-9_\-]*$  np. "R-auction-qty-1"
type RuleId = str


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Rule:
    """
    Reguła Horna: head :- body [, constraints].

    Schemat: $defs/Rule
    - id:          identyfikator reguły, wzorzec ^[A-Za-z][A-Za-z0-9_\\-]*$
    - head:        atom w głowie reguły (konkluzja)
    - body:        lista atomów w ciele reguły (przesłanki)
    - constraints: opcjonalne ograniczenia nie-Hornowskie (preferowane: pusta lista)
    - provenance:  źródło w dokumencie
    - assumptions: założenia ograniczone do tej reguły
    - notes:       dodatkowe uwagi (opcjonalnie)

    Reguła Horna:  head ← body[0] ∧ body[1] ∧ ... ∧ body[n]
    Negacja (NAF): atom z negated=True interpretowany jako 'not atom(args)'
    """
    id: RuleId
    head: Atom
    body: list[Atom]
    constraints: list[str]
    provenance: Provenance
    assumptions: list[ScopedAssumption]
    notes: str | None = None

    @property
    def is_fact(self) -> bool:
        """True gdy ciało jest puste — reguła jest bezwarunkowym faktem."""
        return len(self.body) == 0

    @property
    def negated_body_atoms(self) -> list[Atom]:
        """Atomy w ciele z negated=True (NAF)."""
        return [a for a in self.body if a.negated]

    @property
    def positive_body_atoms(self) -> list[Atom]:
        """Atomy w ciele bez negacji."""
        return [a for a in self.body if not a.negated]
