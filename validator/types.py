"""
validator/types.py — kody błędów i struktury raportu walidacji.

ValidationError — pojedynczy błąd z kodem, ścieżką JSON Pointer,
    komunikatem i mechaniczną instrukcją naprawy.
ValidationReport — wynik walidacji: is_valid, errors, warnings,
    opcjonalnie znormalizowana reguła.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stałe kody błędów walidatora (stage A–F)."""

    # A — JSON Schema
    SCHEMA_VIOLATION              = "E_SCHEMA_VIOLATION"

    # B — predykaty i arność
    PRED_UNKNOWN                  = "E_PRED_UNKNOWN"
    ARITY_MISMATCH                = "E_ARITY_MISMATCH"
    PRED_NOT_ALLOWED_IN_HEAD      = "E_PRED_NOT_ALLOWED_IN_HEAD"
    PRED_NOT_ALLOWED_IN_BODY      = "E_PRED_NOT_ALLOWED_IN_BODY"
    NEGATION_NOT_ALLOWED_FOR_PRED = "E_NEGATION_NOT_ALLOWED_FOR_PRED"

    # C — argumenty / enumy
    VAR_NAMING                    = "E_VAR_NAMING"
    ENUM_VALUE_INVALID            = "E_ENUM_VALUE_INVALID"

    # D — safety (range restriction + NAF safety)
    VAR_UNBOUND_HEAD              = "E_VAR_UNBOUND_HEAD"
    VAR_UNBOUND_NEGATED           = "E_VAR_UNBOUND_NEGATED"
    CONSTRAINTS_NOT_EMPTY         = "E_CONSTRAINTS_NOT_EMPTY"

    # E — provenance
    PROVENANCE_EMPTY_UNIT         = "E_PROVENANCE_EMPTY_UNIT"
    PROVENANCE_EMPTY_QUOTE        = "E_PROVENANCE_EMPTY_QUOTE"
    QUOTE_NOT_IN_SOURCE           = "E_QUOTE_NOT_IN_SOURCE"

    # F — assumptions (ScopedAssumption)
    ASSUMPTION_PRED_INVALID       = "E_ASSUMPTION_PRED_INVALID"
    ASSUMPTION_BAD_ATOM_INDEX     = "E_ASSUMPTION_BAD_ATOM_INDEX"
    ASSUMPTION_BAD_ARG_INDEX      = "E_ASSUMPTION_BAD_ARG_INDEX"
    ASSUMPTION_CONST_MISMATCH     = "E_ASSUMPTION_CONST_MISMATCH"
    ASSUMPTION_REQUIRED_CW        = "E_ASSUMPTION_REQUIRED_CLOSED_WORLD"


@dataclass(slots=True)
class ValidationError:
    """
    Pojedynczy błąd walidacji.

    - code:         stały identyfikator klasy błędu (ErrorCode)
    - path:         JSON Pointer do miejsca błędu, np. "/body/0/pred"
    - message:      czytelny opis błędu
    - expected_fix: krótka mechaniczna instrukcja naprawy (dla LLM)
    - details:      opcjonalny słownik z dodatkowymi danymi
    """

    code: ErrorCode
    path: str
    message: str
    expected_fix: str
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class ValidationReport:
    """
    Wynik pełnej walidacji reguły.

    - is_valid:        True gdy brak błędów (warnings nie wpływają)
    - errors:          lista błędów (ValidationError)
    - warnings:        lista komunikatów ostrzegawczych (str)
    - normalized_rule: reguła z wypełnionymi polami domyślnymi
                       (None gdy walidacja schematu nie przeszła)
    """

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_rule: dict[str, Any] | None = None
