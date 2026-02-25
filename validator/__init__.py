"""
validator — walidator reguł Horna względem manifestu predykatów.

Interfejs publiczny:
    ManifestIndex  — indeks wczytanego manifestu predykatów
    RuleValidator  — główny walidator (etapy A–F)
    ValidationReport, ValidationError, ErrorCode — typy raportu

Typowe użycie:
    from validator import ManifestIndex, RuleValidator

    index     = ManifestIndex.from_file("templates-schemas/predykaty-manifest.json")
    schema    = json.loads(Path("templates-schemas/schemat-regula.json").read_text())
    validator = RuleValidator(index, schema)

    report = validator.validate(rule_json, source_text=fragment_text)
    if not report.is_valid:
        for e in report.errors:
            print(e.code, e.path, e.message)
"""

from .types import ErrorCode, ValidationError, ValidationReport
from .manifest_index import ManifestIndex, PredEntry
from .rule_validator import RuleValidator

__all__ = [
    "ErrorCode",
    "ValidationError",
    "ValidationReport",
    "ManifestIndex",
    "PredEntry",
    "RuleValidator",
]
