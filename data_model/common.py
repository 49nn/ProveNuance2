"""
Wspólne typy pierwotne używane przez conditions, rules i predicates.

Mapowanie na schemat: horn_json_v2_with_scoped_assumptions
  $defs: Atom, Provenance, AssumptionType, AssumptionAbout, ScopedAssumption
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Aliasy typów
# ---------------------------------------------------------------------------

# Wzorzec: ^[a-z][a-z0-9_]*\/[1-9][0-9]*$  np. "delivery_status/2"
type PredicateArity = str


# ---------------------------------------------------------------------------
# Atom
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Atom:
    """
    Atom logiczny: pred(args...), opcjonalnie zanegowany (stratified NAF).

    Schemat: $defs/Atom
    - pred:    nazwa predykatu bez arności, wzorzec ^[a-z][a-z0-9_]*$
    - args:    lista argumentów; zmienne zaczynają się od '?', stałe nie
    - negated: jeśli True → zanegowana NAF (not pred(args...))
    """
    pred: str
    args: list[str]
    negated: bool = False


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Provenance:
    """
    Ślad źródła: identyfikator jednostki dokumentu + dosłowny cytat.

    Schemat: $defs/Provenance
    - unit:  identyfikatory jednostek dokumentu, np. ['3.1(b)']
    - quote: krótki dosłowny fragment (bez parafraz), max 400 znaków
    """
    unit: list[str]
    quote: str


# ---------------------------------------------------------------------------
# Assumption
# ---------------------------------------------------------------------------

class AssumptionType(StrEnum):
    """Kategoria założenia. Schemat: $defs/AssumptionType"""
    DATA_CONTRACT        = "data_contract"
    DATA_SEMANTICS       = "data_semantics"
    ENUMERATION          = "enumeration"
    CLOSED_WORLD         = "closed_world"
    EXTERNAL_COMPUTATION = "external_computation"
    CONFLICT_RESOLUTION  = "conflict_resolution"
    MISSING_PREDICATE    = "missing_predicate"


@dataclass(slots=True)
class AssumptionAbout:
    """
    Wskazuje konkretny predykat (i opcjonalnie argument) którego dotyczy założenie.

    Schemat: $defs/AssumptionAbout
    - pred:       predykat z arnością, np. "delivery_status/2"
    - atom_index: 0-based indeks atomu w ciele reguły (opcjonalnie)
    - arg_index:  1-based indeks argumentu w atomie (opcjonalnie)
    - const:      konkretna wartość stałej (opcjonalnie)
    """
    pred: PredicateArity
    atom_index: int | None = None
    arg_index: int | None = None
    const: str | None = None


@dataclass(slots=True)
class ScopedAssumption:
    """
    Założenie ograniczone do konkretnego miejsca w regule lub warunku.

    Schemat: $defs/ScopedAssumption
    - about: co dotyczy założenia
    - type:  kategoria założenia
    - text:  treść założenia (po polsku lub angielsku)
    """
    about: AssumptionAbout
    type: AssumptionType
    text: str
