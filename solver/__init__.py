"""
solver — silnik Datalog dla ProveNuance2.

Publiczne API:
  Evaluator(rules, facts, conditions)   klasa solvera
  load_facts_json(path)                 → (case_id, domain, Facts)
  load_rules_from_db(conn, ...)         → list[Rule]
  load_derived_rules_from_db(conn, ...) → list[Rule]
  load_conditions_from_db(conn)         → dict[str, list[Atom]]
  parse_goal(goal_str)                  → (pred, args_tuple)
  Atom, Rule                            typy danych
"""

from .engine  import Evaluator, BUILTINS
from .loader  import (
    load_facts_json,
    load_rules_from_db,
    load_derived_rules_from_db,
    load_conditions_from_db,
    parse_goal,
)
from .types   import Atom, Rule

__all__ = [
    "Evaluator",
    "BUILTINS",
    "load_facts_json",
    "load_rules_from_db",
    "load_derived_rules_from_db",
    "load_conditions_from_db",
    "parse_goal",
    "Atom",
    "Rule",
]
