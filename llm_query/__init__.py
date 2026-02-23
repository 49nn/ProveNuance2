"""
llm_query — budowanie promptów i integracja z modelami językowymi.

Publiczne API:
  build_prompt(domain, conditions, fragment) -> str
  fetch_predicates(domain)                  -> list[str]
  read_conditions(path)                     -> str
  read_fragment(path)                       -> str
"""

from .prompt import (
    build_prompt,
    fetch_predicates,
    read_conditions,
    read_fragment,
    TEMPLATE_PATH,
)

__all__ = [
    "build_prompt",
    "fetch_predicates",
    "read_conditions",
    "read_fragment",
    "TEMPLATE_PATH",
]
