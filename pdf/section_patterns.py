"""
pdf/section_patterns.py — wzorce regex do rozpoznawania nagłówków sekcji.

Każdy SectionPattern zawiera:
  - regex       : skompilowany wzorzec (dopasowanie na początku linii)
  - extract_unit: funkcja wyciągająca identyfikator sekcji z Match
  - level       : głębokość hierarchii (1 = najwyższy)

Wzorce są testowane w kolejności; pierwsza pasująca wygrywa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class SectionPattern:
    regex: re.Pattern[str]
    extract_unit: Callable[[re.Match[str]], str]
    level: int


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


def _m(group: int = 0) -> Callable[[re.Match[str]], str]:
    """Wyciąga dopasowanie (lub grupę) i normalizuje białe znaki."""
    def _extract(m: re.Match[str]) -> str:
        text = m.group(group) if group else m.group()
        return re.sub(r"\s+", "", text).strip()
    return _extract


PATTERNS: list[SectionPattern] = [
    # -------------------------------------------------------------------------
    # Poziom 1 — top-level: Art. N, § N, Rozdział N
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(Art\.\s*\d+[a-z]?)"),
        extract_unit=lambda m: re.sub(r"\s+", "", m.group(1)),
        level=1,
    ),
    SectionPattern(
        regex=_p(r"^(§\s*\d+[a-z]?)"),
        extract_unit=lambda m: re.sub(r"\s+", "", m.group(1)),
        level=1,
    ),
    SectionPattern(
        regex=_p(r"^(Rozdzia[łl]\s+\w+)"),
        extract_unit=lambda m: re.sub(r"\s+", " ", m.group(1)).strip(),
        level=1,
    ),
    SectionPattern(
        regex=_p(r"^(ROZDZIA[ŁL]\s+\w+)"),
        extract_unit=lambda m: re.sub(r"\s+", " ", m.group(1)).strip(),
        level=1,
    ),

    # -------------------------------------------------------------------------
    # Poziom 1 — pojedyncza cyfra z kropką: "3."
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(\d+)\.\s+\S"),
        extract_unit=lambda m: m.group(1) + ".",
        level=1,
    ),

    # -------------------------------------------------------------------------
    # Poziom 3 — N.N(x): "3.1(b)" lub N.N.N: "3.1.2"
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(\d+\.\d+\([a-z]\))"),
        extract_unit=lambda m: re.sub(r"\s+", "", m.group(1)),
        level=3,
    ),
    SectionPattern(
        regex=_p(r"^(\d+\.\d+\.\d+)"),
        extract_unit=lambda m: m.group(1),
        level=3,
    ),

    # -------------------------------------------------------------------------
    # Poziom 2 — N.N: "3.1"
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(\d+\.\d+)\s+\S"),
        extract_unit=lambda m: m.group(1),
        level=2,
    ),

    # -------------------------------------------------------------------------
    # Poziom 2–3 — ust. N, pkt N)
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(ust\.\s*\d+)"),
        extract_unit=lambda m: re.sub(r"\s+", "", m.group(1)),
        level=2,
    ),
    SectionPattern(
        regex=_p(r"^(pkt\s+\d+\))"),
        extract_unit=lambda m: re.sub(r"\s+", " ", m.group(1)).strip(),
        level=3,
    ),

    # -------------------------------------------------------------------------
    # Poziom 4 — samodzielne litery: a), (i), (ii)
    # -------------------------------------------------------------------------
    SectionPattern(
        regex=_p(r"^(\([ivxlcdm]+\))"),
        extract_unit=lambda m: m.group(1),
        level=4,
    ),
    SectionPattern(
        regex=_p(r"^([a-z]\))"),
        extract_unit=lambda m: m.group(1),
        level=4,
    ),
]
