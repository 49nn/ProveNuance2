"""
solver/types.py — podstawowe typy danych solvera Datalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Atom:
    """Atom logiczny: pred(arg1, arg2, ...) lub not pred(...)."""
    pred:    str
    args:    tuple[str, ...]
    negated: bool = False

    def __str__(self) -> str:
        prefix = "not " if self.negated else ""
        return f"{prefix}{self.pred}({', '.join(self.args)})"

    def is_ground(self) -> bool:
        """Zwraca True gdy wszystkie argumenty są stałymi (bez prefiksu '?')."""
        return all(not a.startswith("?") for a in self.args)


@dataclass
class Rule:
    """Reguła Horna: head :- body."""
    rule_id:     str
    fragment_id: str
    head_pred:   str
    head_args:   tuple[str, ...]
    body:        list[Atom]

    def __str__(self) -> str:
        head  = f"{self.head_pred}({', '.join(self.head_args)})"
        body  = ", ".join(str(a) for a in self.body)
        label = f"[{self.rule_id}] " if self.rule_id else ""
        return f"{label}{head} :- {body}."

    def head_is_ground(self, subst: dict[str, str]) -> bool:
        from solver.engine import _walk
        return all(not _walk(a, subst).startswith("?") for a in self.head_args)
