"""
data_model/documents.py — model spanów dokumentu (sekcji PDF).

DocumentSpan odpowiada jednej sekcji dokumentu; zbiór spanów tworzy SpanTree.
Pole `unit` jest identyfikatorem sekcji (np. "3.1(b)") używanym jako
provenance.unit w extractorze reguł.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DocumentSpan:
    unit: str            # identyfikator sekcji np. "3.1(b)" → provenance.unit
    title: str           # tekst nagłówka (bez treści sekcji)
    content: str         # treść sekcji (bez nagłówka)
    level: int           # głębokość hierarchii (1..4+)
    parent_unit: str | None
    page_start: int      # 1-based
    page_end: int


# Kolekcja spanów w kolejności dokumentu.
type SpanTree = list[DocumentSpan]
