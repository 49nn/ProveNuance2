"""
llm_query — budowanie promptów i integracja z modelami językowymi.

Publiczne API:
  build_prompt(domain, conditions, fragment) -> str
  fetch_predicates(domain)                  -> list[str]
  read_conditions(path)                     -> str
  read_fragment(path)                       -> str
  call_gemini(prompt, model, api_key)       -> str
"""

from .prompt import (
    build_prompt,
    fetch_predicates,
    read_conditions,
    read_fragment,
    TEMPLATE_PATH,
)
from .gemini import call_gemini, DEFAULT_MODEL

__all__ = [
    "build_prompt",
    "fetch_predicates",
    "read_conditions",
    "read_fragment",
    "TEMPLATE_PATH",
    "call_gemini",
    "DEFAULT_MODEL",
]
