"""
llm_query/gemini.py — wywołanie Gemini API.

Zmienna środowiskowa:
  GEMINI_API_KEY   klucz API (wymagany)

Opcjonalnie plik .env w katalogu głównym projektu:
  GEMINI_API_KEY=AIza...

Publiczne API:
  call_gemini(prompt, model, api_key) -> str
"""

from __future__ import annotations

import os
import pathlib

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv opcjonalne; zmienna może być ustawiona w środowisku

try:
    from google import genai as _genai
except ImportError as _exc:
    raise ImportError(
        "Brakuje pakietu google-genai. Zainstaluj: pip install google-genai"
    ) from _exc


DEFAULT_MODEL = "gemini-2.0-flash"
_ENV_KEY      = "GEMINI_API_KEY"


def call_gemini(
    prompt: str,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> str:
    """
    Wysyła prompt do Gemini i zwraca odpowiedź jako string.

    Args:
        prompt:  Gotowy prompt tekstowy.
        model:   Identyfikator modelu (domyślnie gemini-2.0-flash).
        api_key: Klucz API; jeśli None, odczytywany z GEMINI_API_KEY.

    Returns:
        Tekst odpowiedzi modelu.

    Raises:
        ValueError: Brak klucza API.
        google.genai.errors.APIError: Błąd po stronie API.
    """
    key = api_key or os.getenv(_ENV_KEY)
    if not key:
        raise ValueError(
            f"Brak klucza Gemini API. "
            f"Ustaw zmienną środowiskową {_ENV_KEY} lub przekaż api_key."
        )

    client   = _genai.Client(api_key=key)
    response = client.models.generate_content(model=model, contents=prompt)
    return response.text
