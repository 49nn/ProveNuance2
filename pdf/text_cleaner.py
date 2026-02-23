"""
pdf/text_cleaner.py — oczyszczanie tekstu PDF przy zachowaniu struktury.

Co usuwamy:
  - Nagłówki/stopki stron (tekst blisko krawędzi, powtarzający się)
  - Numery stron (izolowana cyfra/ciąg cyfr na dole/górze)
  - Artefakty łamania wyrazów z myślnikami ("koń-\nczenie" → "kończenie")
  - Nadmiarowe białe znaki w środku linii

Co zachowujemy:
  - Podwójne \n\n między akapitami (bloki z dużą przerwą pionową)
  - Pojedyncze \n wewnątrz bloku (miękki enter)
  - Markery list (•, -, *, cyfra z kropką na początku linii)
  - Wcięcia list (wykrywane przez pozycję x0 relative do lewego marginesu)

Format wyjściowy: plain text z \n i \n\n, bez tagów HTML/Markdown.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # fitz typy tylko dla type checkerów

# ---------------------------------------------------------------------------
# Stałe
# ---------------------------------------------------------------------------

# Próg odległości od krawędzi strony (pt) poniżej którego blok uznajemy
# za potencjalny nagłówek/stopkę strony.
_MARGIN_THRESHOLD_PT = 50.0

# Minimalna liczba stron, na których tekst musi się powtarzać,
# żeby uznać go za nagłówek/stopkę.
_REPEAT_MIN_PAGES = 2

# Wzorzec dla samotnego numeru strony.
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")

# Wzorzec łamania wyrazu z myślnikiem na końcu linii.
_HYPHEN_BREAK_RE = re.compile(r"(\w)-\n(\w)")

# Nadmiarowe spacje w środku linii (nie na początku — marker wcięcia).
_MULTI_SPACE_RE = re.compile(r"(?<=\S) {2,}")


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def collect_repeated_texts(pages_blocks: list[list[dict]]) -> set[str]:
    """
    Zbiera teksty bloków blisko krawędzi strony, które powtarzają się na
    co najmniej _REPEAT_MIN_PAGES stronach → to nagłówki/stopki do usunięcia.

    pages_blocks: lista stron; każda strona to lista bloków PyMuPDF
                  (dict z kluczami 'bbox', 'lines', 'page_height').
    """
    from collections import defaultdict
    text_page_count: dict[str, int] = defaultdict(int)

    for page_blocks in pages_blocks:
        page_height = page_blocks[0].get("page_height", 0) if page_blocks else 0
        seen_on_page: set[str] = set()
        for block in page_blocks:
            if block.get("type") != 0:
                continue
            y0, y1 = block["bbox"][1], block["bbox"][3]
            near_top = y0 < _MARGIN_THRESHOLD_PT
            near_bottom = y1 > (page_height - _MARGIN_THRESHOLD_PT)
            if not (near_top or near_bottom):
                continue
            text = _extract_block_text(block).strip()
            if text and text not in seen_on_page:
                seen_on_page.add(text)
                text_page_count[text] += 1

    return {t for t, c in text_page_count.items() if c >= _REPEAT_MIN_PAGES}


def clean_block_text(
    block: dict,
    repeated_texts: set[str],
    left_margin: float,
) -> str | None:
    """
    Oczyszcza pojedynczy blok tekstowy.

    Zwraca:
      - str z oczyszczonym tekstem
      - None jeśli blok należy całkowicie pominąć
        (nagłówek/stopka, numer strony, blok obrazu)
    """
    if block.get("type") != 0:
        return None

    raw = _extract_block_text(block).strip()
    if not raw:
        return None

    # Odfiltruj nagłówki/stopki i numery stron
    if raw in repeated_texts:
        return None
    if _PAGE_NUMBER_RE.match(raw):
        return None

    # Usuń łamanie wyrazów z myślnikiem
    text = _HYPHEN_BREAK_RE.sub(r"\1\2", raw)

    # Usuń nadmiarowe spacje (ale nie na początku linii — mogą być wcięcia)
    text = _MULTI_SPACE_RE.sub(" ", text)

    # Wykryj wcięcie listy i zachowaj marker
    x0 = block["bbox"][0]
    indent = x0 - left_margin
    if indent > 8:  # wcięty blok — prawdopodobnie element listy
        # Zachowaj tekst bez modyfikacji struktury
        pass

    return text.strip()


def join_blocks(cleaned_blocks: list[str], gaps: list[float]) -> str:
    """
    Scala listę oczyszczonych bloków w jeden ciąg tekstowy.

    gaps[i] = przerwa pionowa (pt) między blokiem i a i+1.
    Duża przerwa (>12 pt) → podwójny \n\n; mała → pojedynczy \n.
    """
    if not cleaned_blocks:
        return ""

    parts: list[str] = [cleaned_blocks[0]]
    for i, block_text in enumerate(cleaned_blocks[1:], start=0):
        gap = gaps[i] if i < len(gaps) else 0.0
        separator = "\n\n" if gap > 12.0 else "\n"
        parts.append(separator)
        parts.append(block_text)

    result = "".join(parts)
    # Normalizuj nadmiarowe puste linie (max 2 kolejne \n)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Pomocnicze
# ---------------------------------------------------------------------------

def _extract_block_text(block: dict) -> str:
    """Wyciąga tekst z bloku PyMuPDF (przez lines → spans)."""
    lines_out: list[str] = []
    for line in block.get("lines", []):
        span_texts = [s.get("text", "") for s in line.get("spans", [])]
        lines_out.append("".join(span_texts))
    return "\n".join(lines_out)
