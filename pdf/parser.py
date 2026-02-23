"""
pdf/parser.py — ekstrakcja spanów sekcji z dokumentów PDF.

Architektura:
  pdf_path → fitz.open() → strony → bloki tekstu z fontami (PyMuPDF dict)
  → _classify_blocks() → (HEADING | BODY) z poziomem
  → _build_spans() → lista DocumentSpan (content = oczyszczony tekst do następnego headingu)
  → SpanTree

Kluczowe funkcje publiczne:
  parse_pdf(path, doc_id) -> SpanTree
"""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Literal

import fitz  # PyMuPDF

from data_model.documents import DocumentSpan, SpanTree
from pdf.section_patterns import PATTERNS, SectionPattern
from pdf.text_cleaner import (
    collect_repeated_texts,
    clean_block_text,
    join_blocks,
)

# ---------------------------------------------------------------------------
# Typy wewnętrzne
# ---------------------------------------------------------------------------

_BlockKind = Literal["HEADING", "BODY"]


class _ClassifiedBlock:
    __slots__ = ("kind", "level", "unit_id", "raw_text", "page", "bbox", "gap_after", "pattern_matched")

    def __init__(
        self,
        kind: _BlockKind,
        raw_text: str,
        page: int,
        bbox: tuple[float, float, float, float],
        level: int = 0,
        unit_id: str = "",
        gap_after: float = 0.0,
        pattern_matched: bool = False,
    ) -> None:
        self.kind = kind
        self.level = level
        self.unit_id = unit_id
        self.raw_text = raw_text
        self.page = page
        self.bbox = bbox
        self.gap_after = gap_after
        self.pattern_matched = pattern_matched  # True = regex, False = font heurystyki


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def parse_pdf(path: str | Path, doc_id: str) -> SpanTree:
    """
    Parsuje plik PDF i zwraca listę DocumentSpan w kolejności dokumentu.

    Args:
        path:   Ścieżka do pliku PDF.
        doc_id: Identyfikator dokumentu (używany jako doc_id w bazie).
    """
    doc = fitz.open(str(path))
    try:
        return _parse_document(doc, doc_id)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Wewnętrzna implementacja
# ---------------------------------------------------------------------------

def _parse_document(doc: fitz.Document, doc_id: str) -> SpanTree:
    # Krok 1: zbierz surowe bloki ze wszystkich stron
    pages_raw = _extract_pages(doc)

    # Krok 2: zbierz powtarzające się teksty (nagłówki/stopki)
    repeated = collect_repeated_texts(pages_raw)

    # Krok 3: oblicz medianę rozmiaru fontu na całym dokumencie
    median_size = _compute_median_font_size(pages_raw)

    # Krok 4: wyznacz lewy margines dokumentu
    left_margin = _compute_left_margin(pages_raw)

    # Krok 5: klasyfikuj bloki
    classified = _classify_all_blocks(pages_raw, repeated, median_size, left_margin)

    # Krok 6: scal kolejne font-nagłówki w jeden (np. tytuł na kilku liniach)
    classified = _merge_font_headings(classified)

    # Krok 7: zbuduj SpanTree
    return _build_spans(classified, doc_id)


def _extract_pages(doc: fitz.Document) -> list[list[dict]]:
    """Zwraca listę stron; każda strona to lista bloków PyMuPDF (dict)."""
    pages: list[list[dict]] = []
    for page in doc:
        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        height = page.rect.height
        blocks: list[dict] = []
        for block in page_dict.get("blocks", []):
            block["page_height"] = height
            block["page_number"] = page.number + 1  # 1-based
            blocks.append(block)
        pages.append(blocks)
    return pages


def _compute_median_font_size(pages_raw: list[list[dict]]) -> float:
    sizes: list[float] = []
    for page_blocks in pages_raw:
        for block in page_blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("size", 0.0)
                    if s > 0:
                        sizes.append(s)
    return statistics.median(sizes) if sizes else 12.0


def _compute_left_margin(pages_raw: list[list[dict]]) -> float:
    x0_values: list[float] = []
    for page_blocks in pages_raw:
        for block in page_blocks:
            if block.get("type") != 0:
                continue
            x0 = block["bbox"][0]
            if x0 > 0:
                x0_values.append(x0)
    if not x0_values:
        return 0.0
    # Użyj 10. percentyla jako estymaty lewego marginesu
    x0_values.sort()
    idx = max(0, int(len(x0_values) * 0.10) - 1)
    return x0_values[idx]


def _classify_all_blocks(
    pages_raw: list[list[dict]],
    repeated: set[str],
    median_size: float,
    left_margin: float,
) -> list[_ClassifiedBlock]:
    result: list[_ClassifiedBlock] = []
    for page_blocks in pages_raw:
        prev_y1: float | None = None
        for block in page_blocks:
            page_no = block.get("page_number", 1)
            bbox = tuple(block["bbox"])
            gap = (bbox[1] - prev_y1) if prev_y1 is not None else 0.0
            prev_y1 = bbox[3]

            text = _get_block_text_raw(block)
            cleaned = clean_block_text(block, repeated, left_margin)
            if cleaned is None:
                continue

            heading_info = _detect_heading(block, text, median_size)
            if heading_info:
                level, unit_id, pattern_matched = heading_info
                result.append(_ClassifiedBlock(
                    kind="HEADING",
                    level=level,
                    unit_id=unit_id,
                    raw_text=cleaned,
                    page=page_no,
                    bbox=bbox,
                    gap_after=0.0,
                    pattern_matched=pattern_matched,
                ))
            else:
                result.append(_ClassifiedBlock(
                    kind="BODY",
                    raw_text=cleaned,
                    page=page_no,
                    bbox=bbox,
                    gap_after=gap,
                ))

    return result


def _detect_heading(
    block: dict,
    text: str,
    median_size: float,
) -> tuple[int, str, bool] | None:
    """
    Wykrywa, czy blok jest nagłówkiem sekcji.

    Priorytet:
      1. Dopasowanie do wzorca sekcji (regex) → niezależnie od fontu.
      2. Heurystyki fontu (rozmiar lub bold) → jeśli brak wzorca.

    Zwraca (level, unit_id, pattern_matched) lub None.
    pattern_matched=True  → trafiony przez regex (numerowany)
    pattern_matched=False → trafiony przez font heurystyki (nienumerowany)
    """
    stripped = text.strip()
    if not stripped:
        return None

    # Warstwa 1: wzorzec regex
    for pat in PATTERNS:
        m = pat.regex.match(stripped)
        if m:
            unit_id = _normalise_unit(pat.extract_unit(m))
            return pat.level, unit_id, True

    # Warstwa 2: heurystyki fontu — tylko dla KRÓTKICH bloków (nagłówki).
    # Długi tekst to akapit, nawet jeśli zawiera pogrubione fragmenty.
    if len(stripped) > 120 or len(stripped.split()) > 18:
        return None

    max_size, bold_ratio = _font_metrics(block)

    # Rozmiar wyraźnie większy od mediany → nagłówek niezależnie od bold.
    if max_size > median_size + 1.5:
        unit_id = _normalise_unit(stripped[:60])
        level = 1 if max_size > median_size + 3 else 2
        return level, unit_id, False

    # Bold tylko jeśli WIĘKSZOŚĆ tekstu jest pogrubiona (≥ 80 %).
    if bold_ratio >= 0.8 and max_size >= median_size:
        unit_id = _normalise_unit(stripped[:60])
        return 2, unit_id, False

    return None


def _font_metrics(block: dict) -> tuple[float, float]:
    """Zwraca (max_rozmiar_fontu, bold_ratio) dla bloku.

    bold_ratio = udział znaków w pogrubionych spanach (0.0 – 1.0).
    Pozwala odróżnić blok całkowicie pogrubiony (nagłówek) od akapitu
    z pojedynczym pogrubionym wyrazem.
    """
    max_size = 0.0
    total_chars = 0
    bold_chars = 0
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            size = span.get("size", 0.0)
            flags = span.get("flags", 0)
            text = span.get("text", "")
            n = len(text)
            if size > max_size:
                max_size = size
            total_chars += n
            if flags & (1 << 4):  # bit 4 = bold w PyMuPDF
                bold_chars += n
    bold_ratio = bold_chars / total_chars if total_chars else 0.0
    return max_size, bold_ratio


def _normalise_unit(text: str) -> str:
    """Normalizuje identyfikator sekcji, np. "3.1 (b)" → "3.1(b)"."""
    # Usuń spacje wokół nawiasów
    text = re.sub(r"\s*\(\s*", "(", text)
    text = re.sub(r"\s*\)\s*", ")", text)
    # Usuń spacje między cyfrą a kropką
    text = re.sub(r"(\d)\s+\.", r"\1.", text)
    # Wielokrotne spacje → jedna
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _get_block_text_raw(block: dict) -> str:
    lines_out: list[str] = []
    for line in block.get("lines", []):
        span_texts = [s.get("text", "") for s in line.get("spans", [])]
        lines_out.append("".join(span_texts))
    return "\n".join(lines_out)


# ---------------------------------------------------------------------------
# Scalanie nagłówków font-heurystycznych
# ---------------------------------------------------------------------------

def _merge_font_headings(classified: list[_ClassifiedBlock]) -> list[_ClassifiedBlock]:
    """
    Scala kolejne bloki-nagłówki wykryte wyłącznie heurystykami fontu
    (pattern_matched=False) w jeden nagłówek.

    Przypadek: tytuł dokumentu rozłożony na kilka krótkich linii/bloków:
      "REGULAMIN UCZESTNICTWA W WYDARZENIACH Z CYKLU"
      "AKADEMIA MANAGERA PR HORYZONT EUROPA"
      "EDYCJA 4"
    → jeden span z tytułem jako unit_id.

    Nagłówki regex (numerowane, np. "Art. 3", "3.1") NIE są scalane.
    """
    result: list[_ClassifiedBlock] = []
    i = 0
    while i < len(classified):
        block = classified[i]

        # Tylko nienumerowane nagłówki font-heurystyczne są kandydatami
        if block.kind != "HEADING" or block.pattern_matched:
            result.append(block)
            i += 1
            continue

        # Zbierz następne bezpośrednio sąsiadujące bloki tego samego typu
        group: list[_ClassifiedBlock] = [block]
        j = i + 1
        while j < len(classified):
            nxt = classified[j]
            if nxt.kind == "HEADING" and not nxt.pattern_matched:
                group.append(nxt)
                j += 1
            else:
                break

        if len(group) == 1:
            result.append(block)
        else:
            # Scal teksty separatorem spacji (zachowuje czytelność)
            merged_text = " ".join(b.raw_text.strip() for b in group)
            unit_id = _normalise_unit(merged_text[:60])
            merged = _ClassifiedBlock(
                kind="HEADING",
                level=group[0].level,
                unit_id=unit_id,
                raw_text=merged_text,
                page=group[0].page,
                bbox=group[0].bbox,
                gap_after=0.0,
                pattern_matched=False,
            )
            result.append(merged)

        i = j

    return result


# ---------------------------------------------------------------------------
# Budowanie SpanTree
# ---------------------------------------------------------------------------

def _build_spans(classified: list[_ClassifiedBlock], doc_id: str) -> SpanTree:
    """
    Scala sklasyfikowane bloki w listę DocumentSpan.
    Każdy heading otwiera nową sekcję; treść akapitów idzie do content bieżącej.

    Duplikaty unit_id (np. wielokrotne "a)" w dokumencie) dostają sufiks "#N",
    żeby zachować unikalność wymaganą przez UNIQUE (doc_id, unit) w bazie.
    """
    spans: list[DocumentSpan] = []
    # Stos (level, unit_id) dla obliczenia parent_unit
    heading_stack: list[tuple[int, str]] = []
    # Licznik wystąpień każdego unit_id w tym dokumencie
    seen_units: dict[str, int] = {}

    # Bufor bieżącej sekcji
    current_heading: _ClassifiedBlock | None = None
    current_unit: str = ""   # unikalny unit_id bieżącej sekcji
    body_blocks: list[str] = []
    body_gaps: list[float] = []
    page_end: int = 1

    def _make_unique(unit: str) -> str:
        n = seen_units.get(unit, 0) + 1
        seen_units[unit] = n
        return unit if n == 1 else f"{unit}#{n}"

    def _flush() -> None:
        nonlocal current_heading, current_unit, body_blocks, body_gaps
        if current_heading is None:
            body_blocks = []
            body_gaps = []
            return
        content = join_blocks(body_blocks, body_gaps)
        parent = _find_parent(heading_stack, current_heading.level)
        spans.append(DocumentSpan(
            unit=current_unit,
            title=current_heading.raw_text,
            content=content,
            level=current_heading.level,
            parent_unit=parent,
            page_start=current_heading.page,
            page_end=page_end,
        ))
        body_blocks = []
        body_gaps = []

    for block in classified:
        if block.kind == "HEADING":
            _flush()
            page_end = block.page
            unique_uid = _make_unique(block.unit_id)
            # Aktualizuj stos
            while heading_stack and heading_stack[-1][0] >= block.level:
                heading_stack.pop()
            current_heading = block
            current_unit = unique_uid
            heading_stack.append((block.level, unique_uid))
        else:
            if body_blocks:
                body_gaps.append(block.gap_after)
            body_blocks.append(block.raw_text)
            page_end = block.page

    _flush()

    # Obsłuż przypadek dokumentu bez żadnego nagłówka
    if not spans and body_blocks:
        content = join_blocks(body_blocks, body_gaps)
        spans.append(DocumentSpan(
            unit="__doc__",
            title="(cały dokument)",
            content=content,
            level=1,
            parent_unit=None,
            page_start=1,
            page_end=page_end,
        ))

    return spans


def _find_parent(
    stack: list[tuple[int, str]],
    level: int,
) -> str | None:
    """Zwraca unit_id najbliższego przodka o mniejszym poziomie."""
    for lvl, uid in reversed(stack):
        if lvl < level:
            return uid
    return None
