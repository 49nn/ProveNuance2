"""
data_model — struktury danych modelu ProveNuance2.

Użycie:
  from data_model import Rule, ConditionDefinition, PredicateSpec, ...

Moduły:
  common     — Atom, Provenance, AssumptionType, AssumptionAbout, ScopedAssumption
  conditions — ConditionDefinition, ConditionDictionary, NewConditionDefinition
  rules      — Rule
  predicates — PredicateSpec, DerivedPredicate, ArgType, PredicateIO,
               PredicateKind, DomainScope, AllowedIn, ValueDomain

Mapowanie na schemat: horn_json_v2_with_scoped_assumptions
  fragment_id          → str
  language             → str (enum: "pl")
  condition_dictionary → ConditionDictionary
  rules                → list[Rule]
  new_conditions       → list[NewConditionDefinition]
  derived_predicates   → list[DerivedPredicate]
  assumptions          → list[str]  (globalne; preferowane: puste)
"""

from .common import (
    PredicateArity,
    Atom,
    Provenance,
    AssumptionType,
    AssumptionAbout,
    ScopedAssumption,
)
from .conditions import (
    ConditionId,
    ConditionDefinition,
    ConditionDictionary,
    NewConditionDefinition,
)
from .rules import (
    RuleId,
    Rule,
)
from .predicates import (
    ArgType,
    PredicateIO,
    PredicateKind,
    DomainScope,
    AllowedIn,
    ValueDomain,
    PredicateSpec,
    DerivedPredicate,
)

__all__ = [
    # common
    "PredicateArity",
    "Atom",
    "Provenance",
    "AssumptionType",
    "AssumptionAbout",
    "ScopedAssumption",
    # conditions
    "ConditionId",
    "ConditionDefinition",
    "ConditionDictionary",
    "NewConditionDefinition",
    # rules
    "RuleId",
    "Rule",
    # predicates
    "ArgType",
    "PredicateIO",
    "PredicateKind",
    "DomainScope",
    "AllowedIn",
    "ValueDomain",
    "PredicateSpec",
    "DerivedPredicate",
]
