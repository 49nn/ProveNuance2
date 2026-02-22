"""
Struktury danych dla predykatów (predicates).

Mapowanie na dwa schematy:
  horn_json_v2_with_scoped_assumptions → $defs/DerivedPredicate, PredicateArity
  predicates_manifest_v1               → $defs/PredicateSpec, ArgType, PredicateIO,
                                         PredicateKind, AllowedIn, ValueDomain
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .common import PredicateArity


# ---------------------------------------------------------------------------
# Enumeracje
# ---------------------------------------------------------------------------

class ArgType(StrEnum):
    """
    Typ argumentu predykatu.
    Schemat predykaty-manifest: $defs/ArgType
    """
    ENTITY      = "entity"
    USER        = "user"
    ACCOUNT     = "account"
    OFFER       = "offer"
    ITEM        = "item"
    PRODUCT     = "product"
    TRANSACTION = "transaction"
    PAYMENT     = "payment"
    DELIVERY    = "delivery"
    BID         = "bid"
    FEE_EVENT   = "fee_event"
    COMPLAINT   = "complaint"
    APPEAL      = "appeal"
    DISCUSSION  = "discussion"
    RATING      = "rating"
    MARKETPLACE = "marketplace"
    STRING      = "string"
    INT         = "int"
    DECIMAL     = "decimal"
    BOOL        = "bool"
    TIME        = "time"
    ENUM        = "enum"
    ANY         = "any"


class PredicateIO(StrEnum):
    """
    Kierunek przepływu danych predykatu.
    Schemat: $defs/PredicateIO
    - INPUT:   dostarczany jako fakt (dane wejściowe)
    - DERIVED: produkowany przez reguły (wyjście)
    - BOTH:    może być faktem lub wnioskiem (używać ostrożnie)
    """
    INPUT   = "input"
    DERIVED = "derived"
    BOTH    = "both"


class PredicateKind(StrEnum):
    """
    Rola predykatu w modelu domeny.
    Schemat: $defs/PredicateKind
    - DOMAIN:    fakty biznesowe / encje
    - CONDITION: podobne do meets_condition (spełnienie warunku)
    - DECISION:  zatwierdzenia / odmowy / eligible
    - UI:        widoczność i dostępność w interfejsie
    - AUDIT:     naruszenia i ślady kontrolne (violates)
    - BUILTIN:   wbudowane porównania (ge, gt, le, lt, eq)
    """
    DOMAIN    = "domain"
    CONDITION = "condition"
    DECISION  = "decision"
    UI        = "ui"
    AUDIT     = "audit"
    BUILTIN   = "builtin"


# ---------------------------------------------------------------------------
# Pomocnicze struktury PredicateSpec
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class AllowedIn:
    """
    Kontroluje gdzie predykat może wystąpić w regułach Horna.
    Schemat: $defs/PredicateSpec/properties/allowed_in
    - head:         może być głową reguły
    - body:         może być w ciele reguły
    - negated_body: może być zanegowany w ciele (NAF)
    """
    head: bool = True
    body: bool = True
    negated_body: bool = False


@dataclass(slots=True)
class ValueDomain:
    """
    Ograniczenie enumeracyjne dla jednego argumentu predykatu.
    Schemat: $defs/PredicateSpec/properties/value_domain
    - enum_arg_index: 1-based indeks argumentu z wyliczeniowymi wartościami
    - allowed_values: lista dopuszczalnych wartości
    """
    enum_arg_index: int
    allowed_values: list[str]


# ---------------------------------------------------------------------------
# PredicateSpec
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PredicateSpec:
    """
    Pełna specyfikacja predykatu z manifestu (predicates_manifest_v1).

    Schemat: $defs/PredicateSpec
    - name:         nazwa bez arności, wzorzec ^[a-z][a-z0-9_]*$
    - arity:        arność 1..16; len(signature) == arity
    - signature:    typy argumentów w kolejności
    - io:           kierunek przepływu danych
    - kind:         rola w modelu domeny
    - pred:         wygodne pole: "name/arity" (opcjonalnie)
    - meaning_pl:   krótki opis semantyczny po polsku
    - allowed_in:   gdzie predykat może wystąpić w regułach
    - value_domain: ograniczenia enumeracyjne dla wybranego argumentu
    - notes:        dodatkowe uwagi
    """
    name: str
    arity: int
    signature: list[ArgType]
    io: PredicateIO
    kind: PredicateKind
    pred: PredicateArity | None = None
    meaning_pl: str | None = None
    allowed_in: AllowedIn = field(default_factory=AllowedIn)
    value_domain: ValueDomain | None = None
    notes: str | None = None

    @property
    def canonical_pred(self) -> PredicateArity:
        """Kanoniczny identyfikator: 'name/arity'."""
        return self.pred if self.pred is not None else f"{self.name}/{self.arity}"

    @property
    def is_input(self) -> bool:
        return self.io == PredicateIO.INPUT

    @property
    def is_derived(self) -> bool:
        return self.io == PredicateIO.DERIVED

    @property
    def can_be_negated_in_body(self) -> bool:
        return self.allowed_in.negated_body


# ---------------------------------------------------------------------------
# DerivedPredicate
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DerivedPredicate:
    """
    Skrócony rekord dla predykatów wyprowadzanych przez reguły.
    Pojawia się w polu derived_predicates odpowiedzi extractora.

    Schemat: horn_json_v2_with_scoped_assumptions → $defs/DerivedPredicate
    - pred:    predykat z arnością, wzorzec ^[a-z][a-z0-9_]*/[1-9][0-9]*$
    - meaning: opis semantyczny (po polsku lub angielsku)
    """
    pred: PredicateArity
    meaning: str

    @property
    def name(self) -> str:
        """Sama nazwa predykatu bez arności."""
        return self.pred.split("/")[0]

    @property
    def arity(self) -> int:
        """Arność predykatu."""
        return int(self.pred.split("/")[1])
