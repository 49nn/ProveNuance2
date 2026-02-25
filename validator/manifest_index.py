"""
validator/manifest_index.py — indeks manifestu predykatów.

ManifestIndex wczytuje predicates_manifest_v1 i buduje słowniki:
  _by_name: name  -> PredEntry
  _by_pred: pred  -> PredEntry  (klucz: "name/arity")

Polityka (policy):
  whitelist_mode    — "allow_only_listed" | "allow_unlisted"
  naf_closed_world  — frozenset predykatów dopuszczonych do NAF przez CWA
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# PredEntry — spłaszczony wpis z manifestu
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PredEntry:
    """
    Spłaszczona reprezentacja PredicateSpec z manifestu.

    - name:                   np. "delivery_status"
    - arity:                  np. 2
    - pred:                   np. "delivery_status/2"
    - io:                     "input" | "derived" | "both"
    - kind:                   "domain" | "condition" | "decision" | "ui" | "audit" | "builtin"
    - allowed_in_head:        czy może być głową reguły
    - allowed_in_body:        czy może być w ciele reguły (pozytywnie)
    - allowed_in_negated_body: czy może być zanegowany w ciele (NAF)
    - enum_arg_index:         1-based indeks argumentu enum (None jeśli brak value_domain)
    - allowed_values:         dozwolone wartości enum (None jeśli brak value_domain)
    """

    name: str
    arity: int
    pred: str
    io: str
    kind: str
    allowed_in_head: bool
    allowed_in_body: bool
    allowed_in_negated_body: bool
    enum_arg_index: int | None
    allowed_values: frozenset[str] | None


# ---------------------------------------------------------------------------
# Domyślne allowed_in wg io
# ---------------------------------------------------------------------------

def _default_allowed_in(io: str) -> tuple[bool, bool, bool]:
    """
    Zwraca (head, body, negated_body) dla predykatu bez jawnego allowed_in.

    Logika:
      input   → head=False (fakty EDB nie są wyprowadzane przez reguły)
      derived  → head=True,  negated_body=False
      both     → head=True,  negated_body=True  (ostrożna reguła)
    """
    match io:
        case "input":
            return False, True, False
        case "derived":
            return True, True, False
        case _:  # "both"
            return True, True, True


# ---------------------------------------------------------------------------
# ManifestIndex
# ---------------------------------------------------------------------------

class ManifestIndex:
    """
    Indeks manifestu predykatów do szybkiego wyszukiwania przez walidator.

    Atrybuty publiczne:
      whitelist_mode   — polityka whitelisty ("allow_only_listed" itp.)
      naf_closed_world — frozenset<str>: predykaty "name/arity" z listy CWA
    """

    def __init__(self, manifest: dict) -> None:
        policy = manifest.get("policy", {})
        self.whitelist_mode: str = policy.get("whitelist_mode", "allow_only_listed")
        self.naf_closed_world: frozenset[str] = frozenset(
            policy.get("naf_closed_world_predicates", [])
        )

        self._by_name: dict[str, PredEntry] = {}
        self._by_pred: dict[str, PredEntry] = {}

        for p in manifest.get("predicates", []):
            entry = self._build_entry(p)
            self._by_name[entry.name] = entry
            self._by_pred[entry.pred] = entry

    # ------------------------------------------------------------------
    # Budowa wpisu
    # ------------------------------------------------------------------

    def _build_entry(self, p: dict) -> PredEntry:
        name  = p["name"]
        arity = p["arity"]
        pred  = p.get("pred") or f"{name}/{arity}"
        io    = p.get("io", "input")
        kind  = p.get("kind", "domain")

        ai = p.get("allowed_in")
        if ai is not None:
            head         = bool(ai.get("head", True))
            body         = bool(ai.get("body", True))
            negated_body = bool(ai.get("negated_body", False))
        else:
            head, body, negated_body = _default_allowed_in(io)

        vd = p.get("value_domain")
        enum_arg_index = None
        allowed_values = None
        if vd:
            enum_arg_index = vd.get("enum_arg_index")
            allowed_values = frozenset(vd.get("allowed_values", []))

        return PredEntry(
            name=name,
            arity=arity,
            pred=pred,
            io=io,
            kind=kind,
            allowed_in_head=head,
            allowed_in_body=body,
            allowed_in_negated_body=negated_body,
            enum_arg_index=enum_arg_index,
            allowed_values=allowed_values,
        )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup_by_name(self, name: str) -> PredEntry | None:
        """Szuka wpisu po nazwie predykatu (bez arności)."""
        return self._by_name.get(name)

    def lookup_by_pred(self, pred_with_arity: str) -> PredEntry | None:
        """Szuka wpisu po 'name/arity'."""
        return self._by_pred.get(pred_with_arity)

    def is_naf_closed_world(self, pred_with_arity: str) -> bool:
        """Czy predykat (w formacie 'name/arity') jest na liście CWA?"""
        return pred_with_arity in self.naf_closed_world

    # ------------------------------------------------------------------
    # Konstruktory fabryczne
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> "ManifestIndex":
        """Ładuje manifest z pliku JSON."""
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return cls(data)

    @classmethod
    def from_dict(cls, manifest: dict) -> "ManifestIndex":
        """Buduje indeks z już wczytanego słownika."""
        return cls(manifest)
