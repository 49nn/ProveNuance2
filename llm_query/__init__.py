"""
llm_query — budowanie promptów i integracja z modelami językowymi.

Publiczne API:
  build_prompt(domain, conditions, fragment)      -> str
  fetch_predicates(domain)                        -> list[str]
  read_conditions(path)                           -> str
  read_fragment(path)                             -> str
  call_gemini(prompt, model, api_key)             -> str
  collect_constants(result)                       -> dict[str, str | None]
  upsert_constants(conn, constants, domain)       -> int
  collect_assumptions(result)                     -> list[dict]
  upsert_assumptions(conn, assumptions, domain)   -> int
  collect_rules(result)                           -> list[dict]
  upsert_rules(conn, rules, domain)               -> int
  collect_conditions(result)                      -> list[dict]
  upsert_conditions(conn, conditions, domain)     -> int
"""

from .prompt import (
    build_prompt,
    fetch_predicates,
    read_conditions,
    read_fragment,
    TEMPLATE_PATH,
)
from .gemini import call_gemini, DEFAULT_MODEL
from .constants import collect_constants, upsert_constants
from .assumptions import collect_assumptions, upsert_assumptions
from .rules import collect_rules, upsert_rules
from .conditions_store import collect_conditions, upsert_conditions
from .derived_predicates import collect_derived_predicates, upsert_derived_predicates

__all__ = [
    "build_prompt",
    "fetch_predicates",
    "read_conditions",
    "read_fragment",
    "TEMPLATE_PATH",
    "call_gemini",
    "DEFAULT_MODEL",
    "collect_constants",
    "upsert_constants",
    "collect_assumptions",
    "upsert_assumptions",
    "collect_rules",
    "upsert_rules",
    "collect_conditions",
    "upsert_conditions",
    "collect_derived_predicates",
    "upsert_derived_predicates",
]
