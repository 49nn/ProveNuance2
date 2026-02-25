"""html_parser/parser.py — parsowanie strony HTML do spanów sekcji."""

from __future__ import annotations

import re
import unicodedata

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

from data_model.documents import DocumentSpan, SpanTree

# Tagi blokowe (determinują granice bloków treści)
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_HEADING_LEVEL: dict[str, int] = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_TAGS: set[str] = {
    "div", "p", "article", "section", "main", "aside", "nav",
    "header", "footer", "blockquote",
    "li", "ul", "ol",
    "td", "th", "tr", "table",
    "form", "fieldset", "details", "summary",
} | _HEADING_TAGS

# Tagi zawierające szum (nie treść)
_NOISE_TAGS = {"script", "style", "noscript"}


def _slugify(text: str, max_len: int = 60) -> str:
    """Zamień tekst nagłówka na bezpieczny identyfikator ASCII."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text[:max_len].rstrip("-") or "span"


def _extract_blocks(body: Tag) -> list[tuple[bool, int, str]]:
    """
    Przechodzi drzewo DOM i zwraca spłaszczoną listę bloków:
      (is_heading, level, text)

    Reguła unikania duplikowania treści:
    - Nagłówek (h1–h6): emituje cały swój tekst, bez rekurencji w dzieci.
    - Blok liściasty (brak blokowych dzieci): emituje cały swój tekst.
    - Blok kontenerowy (ma blokowe dzieci): rekuruje w dzieci, sam nie emituje.
    """
    blocks: list[tuple[bool, int, str]] = []

    def walk(el: Tag) -> None:
        name = el.name
        if name in _NOISE_TAGS:
            return
        if name in _HEADING_TAGS:
            text = el.get_text(" ", strip=True)
            if text:
                blocks.append((True, _HEADING_LEVEL[name], text))
            return  # nie rekurujemy w nagłówki
        if name in _BLOCK_TAGS:
            has_block_child = any(
                isinstance(c, Tag) and c.name in _BLOCK_TAGS
                for c in el.children
            )
            if not has_block_child:
                text = el.get_text(" ", strip=True)
                if text:
                    blocks.append((False, 0, text))
            else:
                for child in el.children:
                    if isinstance(child, Tag):
                        walk(child)
        else:
            # niebloKowy element (body, html, span itp.) — rekurujemy
            for child in el.children:
                if isinstance(child, Tag):
                    walk(child)

    for child in body.children:
        if isinstance(child, Tag):
            walk(child)

    return blocks


def _build_spantree(blocks: list[tuple[bool, int, str]]) -> SpanTree:
    """Konwertuje spłaszczoną listę bloków na SpanTree."""
    spans: SpanTree = []
    unit_seen: dict[str, int] = {}
    # stos: (poziom_nagłówka, indeks_spanu)
    stack: list[tuple[int, int]] = []

    def make_unit(title: str) -> str:
        base = _slugify(title) if title else "span"
        n = unit_seen.get(base, 0)
        unit_seen[base] = n + 1
        return base if n == 0 else f"{base}#{n}"

    def append_to_current(text: str) -> None:
        idx = stack[-1][1] if stack else (len(spans) - 1 if spans else None)
        if idx is not None:
            s = spans[idx]
            s.content = (s.content + "\n\n" + text) if s.content else text

    # Indeks pierwszego nagłówka
    first_h = next((i for i, (h, _, _) in enumerate(blocks) if h), None)

    # Treść przed pierwszym nagłówkiem → span "intro"
    intro_end = first_h if first_h is not None else len(blocks)
    intro_texts = [t for _, _, t in blocks[:intro_end]]
    if intro_texts:
        unit_seen["intro"] = 1
        spans.append(DocumentSpan(
            unit="intro",
            title="",
            content="\n\n".join(intro_texts),
            level=1,
            parent_unit=None,
            page_start=1,
            page_end=1,
        ))

    start = first_h if first_h is not None else len(blocks)
    for is_heading, level, text in blocks[start:]:
        if is_heading:
            # Zdejmuj ze stosu sekcje na tym samym lub głębszym poziomie
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent_unit = spans[stack[-1][1]].unit if stack else None
            unit = make_unit(text)
            spans.append(DocumentSpan(
                unit=unit,
                title=text,
                content="",
                level=level,
                parent_unit=parent_unit,
                page_start=1,
                page_end=1,
            ))
            stack.append((level, len(spans) - 1))
        else:
            append_to_current(text)

    return spans


def parse_html_url(url: str, doc_id: str) -> SpanTree:
    """Pobiera stronę HTML z podanego URL i parsuje ją do SpanTree."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, timeout=30, headers=headers)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup.find_all(_NOISE_TAGS):
        tag.decompose()

    body: Tag = soup.find("body") or soup  # type: ignore[assignment]
    blocks = _extract_blocks(body)
    return _build_spantree(blocks)
