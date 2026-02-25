"""
validator/rule_validator.py — główny walidator reguł Horna.

RuleValidator.validate(rule_json, source_text=None) -> ValidationReport

Etapy:
  A — JSON Schema           (wymaga jsonschema>=4.0; pominięty gdy brak)
  B — predykaty i arność    (head + body: whitelist, arity, allowed_in)
  C — wartości enumów       (value_domain dla konkretnych stałych)
  D — safety Datalog        (range restriction głowy + NAF safety + naming)
  E — provenance            (unit niepuste, quote niepuste, quote w source)
  F — założenia             (ScopedAssumption: referencje + wymuszenie CWA)
"""

from __future__ import annotations

import re
from typing import Any

from .types import ErrorCode, ValidationError, ValidationReport
from .manifest_index import ManifestIndex, PredEntry
from .normalizer import normalize_rule

# Wzorzec poprawnej nazwy zmiennej: ?X, ?Offer1, ?BidPrice itp.
_VAR_RE = re.compile(r"^\?[A-Za-z][A-Za-z0-9_]*$")

# Limit błędów — po przekroczeniu przerywamy dalsze etapy
MAX_ERRORS = 20


# ---------------------------------------------------------------------------
# Funkcje pomocnicze
# ---------------------------------------------------------------------------

def _is_var(arg: str) -> bool:
    return isinstance(arg, str) and arg.startswith("?")


def _is_const(arg: str) -> bool:
    return isinstance(arg, str) and not arg.startswith("?")


def _normalize_ws(s: str) -> str:
    """Normalizacja whitespace do porównania cytatów."""
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# RuleValidator
# ---------------------------------------------------------------------------

class RuleValidator:
    """
    Walidator reguły Horna względem manifestu predykatów.

    Użycie:
        index     = ManifestIndex.from_file("predykaty-manifest.json")
        schema    = json.loads(Path("schemat-regula.json").read_text())
        validator = RuleValidator(index, schema)
        report    = validator.validate(rule_json, source_text=fragment)
    """

    def __init__(
        self,
        index: ManifestIndex,
        rule_schema: dict[str, Any] | None = None,
    ) -> None:
        self._index  = index
        self._schema = rule_schema

    # ------------------------------------------------------------------
    # Publiczny interfejs
    # ------------------------------------------------------------------

    def validate(
        self,
        rule_json: dict[str, Any],
        source_text: str | None = None,
    ) -> ValidationReport:
        """
        Waliduje regułę i zwraca ValidationReport.

        Args:
            rule_json:   słownik (po json.loads) z regułą Horn
            source_text: opcjonalny pełny tekst fragmentu dokumentu
                         (do weryfikacji provenance.quote)
        """
        errors: list[ValidationError] = []
        warnings: list[str] = []

        # A — JSON Schema (fail-fast: brak sensu iść dalej przy błędach schematu)
        if self._schema is not None:
            self._stage_schema(rule_json, errors)
            if errors:
                return ValidationReport(
                    is_valid=False,
                    errors=errors,
                    warnings=warnings,
                    normalized_rule=None,
                )

        rule = normalize_rule(rule_json)

        # B — predykaty i arność
        self._stage_predicates(rule, errors)

        # C — enumy
        if len(errors) < MAX_ERRORS:
            self._stage_enums(rule, errors)

        # D — safety
        if len(errors) < MAX_ERRORS:
            self._stage_safety(rule, errors, warnings)

        # E — provenance
        if len(errors) < MAX_ERRORS:
            self._stage_provenance(rule, errors, source_text)

        # F — assumptions
        if len(errors) < MAX_ERRORS:
            self._stage_assumptions(rule, errors)

        return ValidationReport(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_rule=rule,
        )

    # ------------------------------------------------------------------
    # Stage A — JSON Schema
    # ------------------------------------------------------------------

    def _stage_schema(self, rule_json: dict, errors: list[ValidationError]) -> None:
        try:
            import jsonschema
        except ImportError:
            return  # opcjonalna zależność — pomijamy jeśli brak

        validator = jsonschema.Draft202012Validator(self._schema)
        for e in validator.iter_errors(rule_json):
            path = (
                "/" + "/".join(str(p) for p in e.absolute_path)
                if e.absolute_path
                else "/"
            )
            errors.append(ValidationError(
                code=ErrorCode.SCHEMA_VIOLATION,
                path=path,
                message=e.message,
                expected_fix=f"Popraw naruszenie schematu JSON na ścieżce {path}.",
            ))

    # ------------------------------------------------------------------
    # Stage B — predykaty i arność (head + body)
    # ------------------------------------------------------------------

    def _stage_predicates(self, rule: dict, errors: list[ValidationError]) -> None:
        head = rule.get("head")
        if isinstance(head, dict):
            self._check_atom(head, "/head", in_head=True, errors=errors)

        body = rule.get("body", [])
        for i, atom in enumerate(body):
            if isinstance(atom, dict):
                self._check_atom(atom, f"/body/{i}", in_head=False, errors=errors)

    def _check_atom(
        self,
        atom: dict,
        path: str,
        in_head: bool,
        errors: list[ValidationError],
    ) -> None:
        pred_name = atom.get("pred", "")
        negated   = atom.get("negated", False)
        args      = atom.get("args", [])

        entry = self._index.lookup_by_name(pred_name)
        if entry is None:
            errors.append(ValidationError(
                code=ErrorCode.PRED_UNKNOWN,
                path=f"{path}/pred",
                message=f"Predykat '{pred_name}' nie istnieje w manifeście.",
                expected_fix=(
                    f"Użyj predykatu z manifestu lub dodaj '{pred_name}' do manifestu."
                ),
                details={"pred": pred_name},
            ))
            return  # nie można walidować dalej bez wpisu

        # Arność
        if len(args) != entry.arity:
            errors.append(ValidationError(
                code=ErrorCode.ARITY_MISMATCH,
                path=f"{path}/args",
                message=(
                    f"Predykat '{pred_name}' wymaga {entry.arity} arg(s), "
                    f"podano {len(args)}."
                ),
                expected_fix=f"Podaj dokładnie {entry.arity} argumentów dla '{pred_name}'.",
                details={"expected": entry.arity, "actual": len(args)},
            ))

        # allowed_in
        if in_head:
            if not entry.allowed_in_head:
                errors.append(ValidationError(
                    code=ErrorCode.PRED_NOT_ALLOWED_IN_HEAD,
                    path=f"{path}/pred",
                    message=(
                        f"Predykat '{pred_name}' (io={entry.io}) nie może być "
                        f"głową reguły."
                    ),
                    expected_fix=(
                        "Głową reguły powinien być predykat derived lub both. "
                        "Zmień predykat lub ustaw allowed_in.head=true w manifeście."
                    ),
                    details={"pred": pred_name, "io": entry.io},
                ))
        else:
            if negated:
                if not entry.allowed_in_negated_body and not self._index.is_naf_closed_world(entry.pred):
                    errors.append(ValidationError(
                        code=ErrorCode.NEGATION_NOT_ALLOWED_FOR_PRED,
                        path=f"{path}/pred",
                        message=(
                            f"Negacja (NAF) predykatu '{pred_name}' jest niedozwolona: "
                            f"allowed_in.negated_body=false i predykat nie jest "
                            f"w naf_closed_world."
                        ),
                        expected_fix=(
                            f"Dodaj '{entry.pred}' do policy.naf_closed_world_predicates "
                            f"lub ustaw allowed_in.negated_body=true w manifeście."
                        ),
                        details={"pred": entry.pred},
                    ))
            else:
                if not entry.allowed_in_body:
                    errors.append(ValidationError(
                        code=ErrorCode.PRED_NOT_ALLOWED_IN_BODY,
                        path=f"{path}/pred",
                        message=f"Predykat '{pred_name}' nie może być w ciele reguły.",
                        expected_fix=(
                            f"Sprawdź allowed_in.body dla '{pred_name}' w manifeście."
                        ),
                        details={"pred": pred_name},
                    ))

    # ------------------------------------------------------------------
    # Stage C — wartości enumów
    # ------------------------------------------------------------------

    def _stage_enums(self, rule: dict, errors: list[ValidationError]) -> None:
        head = rule.get("head")
        if isinstance(head, dict):
            self._check_enum_args(head, "/head", errors)

        for i, atom in enumerate(rule.get("body", [])):
            if isinstance(atom, dict):
                self._check_enum_args(atom, f"/body/{i}", errors)

    def _check_enum_args(
        self,
        atom: dict,
        path: str,
        errors: list[ValidationError],
    ) -> None:
        entry = self._index.lookup_by_name(atom.get("pred", ""))
        if entry is None or entry.allowed_values is None:
            return

        k    = entry.enum_arg_index - 1  # 0-based
        args = atom.get("args", [])
        if k < len(args):
            arg = args[k]
            if _is_const(arg) and arg not in entry.allowed_values:
                errors.append(ValidationError(
                    code=ErrorCode.ENUM_VALUE_INVALID,
                    path=f"{path}/args/{k}",
                    message=(
                        f"Wartość '{arg}' jest niedozwolona dla predykatu "
                        f"'{atom.get('pred')}' (argument {k + 1})."
                    ),
                    expected_fix=f"Użyj jednej z: {sorted(entry.allowed_values)}.",
                    details={"allowed": sorted(entry.allowed_values), "got": arg},
                ))

    # ------------------------------------------------------------------
    # Stage D — safety Datalog (range restriction + NAF + naming)
    # ------------------------------------------------------------------

    def _stage_safety(
        self,
        rule: dict,
        errors: list[ValidationError],
        warnings: list[str],
    ) -> None:
        head        = rule.get("head", {}) if isinstance(rule.get("head"), dict) else {}
        body        = rule.get("body", [])
        constraints = rule.get("constraints", [])

        # Zmienne związane przez pozytywne atomy ciała
        pos_vars: set[str] = set()
        for atom in body:
            if not atom.get("negated", False):
                for arg in atom.get("args", []):
                    if _is_var(arg):
                        pos_vars.add(arg)

        # Zmienne w głowie muszą być w pos_vars
        for arg in head.get("args", []):
            if _is_var(arg) and arg not in pos_vars:
                errors.append(ValidationError(
                    code=ErrorCode.VAR_UNBOUND_HEAD,
                    path="/head/args",
                    message=(
                        f"Zmienna '{arg}' w głowie reguły nie jest związana "
                        f"przez żaden pozytywny atom ciała."
                    ),
                    expected_fix=(
                        f"Dodaj pozytywny atom do ciała reguły, "
                        f"który uziemi zmienną '{arg}'."
                    ),
                    details={"var": arg},
                ))

        # Zmienne w zanegowanych atomach muszą być w pos_vars (NAF safety)
        for i, atom in enumerate(body):
            if atom.get("negated", False):
                for arg in atom.get("args", []):
                    if _is_var(arg) and arg not in pos_vars:
                        errors.append(ValidationError(
                            code=ErrorCode.VAR_UNBOUND_NEGATED,
                            path=f"/body/{i}",
                            message=(
                                f"Zmienna '{arg}' w zanegowanym atomie body[{i}] "
                                f"nie jest związana przez pozytywne ciało."
                            ),
                            expected_fix=(
                                f"Dodaj pozytywny atom, który uziemi '{arg}' "
                                f"przed zanegowanym body[{i}]."
                            ),
                            details={"var": arg, "atom_index": i},
                        ))

        # Nazewnictwo zmiennych
        all_atoms: list[tuple[dict, str]] = [
            (head, "/head"),
            *((body[i], f"/body/{i}") for i in range(len(body))),
        ]
        for atom, apath in all_atoms:
            for arg in atom.get("args", []):
                if _is_var(arg) and not _VAR_RE.match(arg):
                    errors.append(ValidationError(
                        code=ErrorCode.VAR_NAMING,
                        path=f"{apath}/args",
                        message=(
                            f"Zmienna '{arg}' nie pasuje do wzorca "
                            r"^\?[A-Za-z][A-Za-z0-9_]*$."
                        ),
                        expected_fix=(
                            f"Zmień '{arg}' na poprawną zmienną, np. '?X' lub '?Offer1'."
                        ),
                        details={"var": arg},
                    ))

        # Ostrzeżenie o ograniczeniach nie-Hornowskich
        if constraints:
            warnings.append(
                f"Reguła zawiera {len(constraints)} ograniczenie(a) nie-Hornowskie "
                f"(constraints). Preferowana wartość: pusta lista."
            )

    # ------------------------------------------------------------------
    # Stage E — provenance
    # ------------------------------------------------------------------

    def _stage_provenance(
        self,
        rule: dict,
        errors: list[ValidationError],
        source_text: str | None,
    ) -> None:
        prov = rule.get("provenance")
        if not isinstance(prov, dict):
            return

        unit  = prov.get("unit", [])
        quote = prov.get("quote", "")

        if not unit:
            errors.append(ValidationError(
                code=ErrorCode.PROVENANCE_EMPTY_UNIT,
                path="/provenance/unit",
                message=(
                    "provenance.unit jest puste — brak identyfikatora "
                    "jednostki dokumentu."
                ),
                expected_fix=(
                    "Podaj identyfikator sekcji lub paragrafu, "
                    "np. [\"§3 ust. 1(b)\"]."
                ),
            ))

        if not quote or not quote.strip():
            errors.append(ValidationError(
                code=ErrorCode.PROVENANCE_EMPTY_QUOTE,
                path="/provenance/quote",
                message="provenance.quote jest puste — brak cytatu źródłowego.",
                expected_fix=(
                    "Wklej dosłowny, krótki fragment z dokumentu jako cytat "
                    "(max 400 znaków)."
                ),
            ))
        elif source_text:
            if _normalize_ws(quote) not in _normalize_ws(source_text):
                errors.append(ValidationError(
                    code=ErrorCode.QUOTE_NOT_IN_SOURCE,
                    path="/provenance/quote",
                    message=(
                        "Cytat nie znaleziony w tekście źródłowym "
                        "(po normalizacji whitespace)."
                    ),
                    expected_fix=(
                        "Użyj dosłownego fragmentu z tekstu źródłowego jako cytatu."
                    ),
                    details={"quote_preview": quote[:100]},
                ))

    # ------------------------------------------------------------------
    # Stage F — założenia (ScopedAssumption)
    # ------------------------------------------------------------------

    def _stage_assumptions(self, rule: dict, errors: list[ValidationError]) -> None:
        assumptions = rule.get("assumptions", [])
        body        = rule.get("body", [])

        # Predykaty z naf_closed_world użyte pod negacją → wymagają CWA
        negated_cw: set[str] = set()
        for atom in body:
            if atom.get("negated", False):
                entry = self._index.lookup_by_name(atom.get("pred", ""))
                if entry and self._index.is_naf_closed_world(entry.pred):
                    negated_cw.add(entry.pred)

        # Zbierz predykaty pokryte closed_world assumptions
        cw_covered: set[str] = set()

        for a_idx, assumption in enumerate(assumptions):
            if not isinstance(assumption, dict):
                continue
            if assumption.get("type") == "closed_world":
                about = assumption.get("about", {})
                cw_covered.add(about.get("pred", ""))
            self._check_assumption(assumption, a_idx, body, errors)

        # Wymuś closed_world assumption dla każdego negowanego CWA predykatu
        for pred in sorted(negated_cw):
            if pred not in cw_covered:
                errors.append(ValidationError(
                    code=ErrorCode.ASSUMPTION_REQUIRED_CW,
                    path="/assumptions",
                    message=(
                        f"Predykat '{pred}' jest użyty pod negacją NAF "
                        f"i należy do naf_closed_world — wymagane założenie "
                        f"type='closed_world'."
                    ),
                    expected_fix=(
                        f"Dodaj do assumptions: "
                        f'{{\"about\": {{\"pred\": \"{pred}\"}}, '
                        f'\"type\": \"closed_world\", \"text\": \"...\"}}.'
                    ),
                    details={"pred": pred},
                ))

    def _check_assumption(
        self,
        assumption: dict,
        a_idx: int,
        body: list,
        errors: list[ValidationError],
    ) -> None:
        about = assumption.get("about", {})
        if not isinstance(about, dict):
            return

        pred_str = about.get("pred", "")

        # Szukaj wpisu po "name/arity", a w razie braku — po samej nazwie
        entry = self._index.lookup_by_pred(pred_str)
        if entry is None and "/" in pred_str:
            entry = self._index.lookup_by_name(pred_str.split("/")[0])

        if entry is None:
            errors.append(ValidationError(
                code=ErrorCode.ASSUMPTION_PRED_INVALID,
                path=f"/assumptions/{a_idx}/about/pred",
                message=f"Predykat '{pred_str}' w założeniu nie istnieje w manifeście.",
                expected_fix=(
                    "Użyj formatu 'name/arity' (np. 'delivery_status/2') "
                    "i upewnij się, że predykat jest w manifeście."
                ),
                details={"pred": pred_str},
            ))
            return

        atom_index = about.get("atom_index")
        arg_index  = about.get("arg_index")
        const      = about.get("const")

        # Walidacja atom_index
        if atom_index is not None:
            if atom_index >= len(body):
                errors.append(ValidationError(
                    code=ErrorCode.ASSUMPTION_BAD_ATOM_INDEX,
                    path=f"/assumptions/{a_idx}/about/atom_index",
                    message=(
                        f"atom_index={atom_index} poza zakresem ciała reguły "
                        f"(body ma {len(body)} atom(ów), indeksy 0..{len(body)-1})."
                    ),
                    expected_fix=f"Użyj atom_index w zakresie 0..{len(body) - 1}.",
                    details={"atom_index": atom_index, "body_len": len(body)},
                ))
                return  # dalsze sprawdzenia wymagają poprawnego atom_index

            # Walidacja arg_index
            if arg_index is not None:
                if arg_index < 1 or arg_index > entry.arity:
                    errors.append(ValidationError(
                        code=ErrorCode.ASSUMPTION_BAD_ARG_INDEX,
                        path=f"/assumptions/{a_idx}/about/arg_index",
                        message=(
                            f"arg_index={arg_index} poza zakresem dla '{entry.pred}' "
                            f"(arity={entry.arity}, dozwolone: 1..{entry.arity})."
                        ),
                        expected_fix=f"Użyj arg_index w zakresie 1..{entry.arity}.",
                        details={"arg_index": arg_index, "arity": entry.arity},
                    ))
                elif const is not None:
                    # Sprawdź zgodność const z argumentem z ciała
                    ref_atom = body[atom_index]
                    if isinstance(ref_atom, dict):
                        ref_args = ref_atom.get("args", [])
                        k = arg_index - 1  # 0-based
                        if k < len(ref_args):
                            actual = ref_args[k]
                            if _is_const(actual) and actual != const:
                                errors.append(ValidationError(
                                    code=ErrorCode.ASSUMPTION_CONST_MISMATCH,
                                    path=f"/assumptions/{a_idx}/about/const",
                                    message=(
                                        f"const='{const}' nie zgadza się z "
                                        f"body[{atom_index}].args[{k}]='{actual}'."
                                    ),
                                    expected_fix=(
                                        f"Zmień const na '{actual}' lub popraw "
                                        f"atom_index/arg_index."
                                    ),
                                    details={"expected": actual, "got": const},
                                ))
