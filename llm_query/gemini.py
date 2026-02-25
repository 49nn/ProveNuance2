"""
llm_query/gemini.py — wywołanie Gemini API.

Zmienna środowiskowa:
  GEMINI_API_KEY   klucz API (wymagany)

Opcjonalnie plik .env w katalogu głównym projektu:
  GEMINI_API_KEY=AIza...

Publiczne API:
  call_gemini(prompt, model, api_key, max_retries) -> str
"""

from __future__ import annotations

import functools
import os
import pathlib
import re
import sys
import time
from typing import Protocol, cast

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env", override=True)
except ImportError:
    pass  # python-dotenv opcjonalne; zmienna może być ustawiona w środowisku

try:
    from google import genai as _genai
    from google.genai import errors as _genai_errors
except ImportError as _exc:
    raise ImportError(
        "Brakuje pakietu google-genai. Zainstaluj: pip install google-genai"
    ) from _exc


DEFAULT_MODEL  = "gemini-2.5-flash"
DEFAULT_RETRIES = 3
_ENV_KEY        = "GEMINI_API_KEY"


@functools.lru_cache(maxsize=4)
def _get_client(api_key: str) -> "_genai.Client":
    """Zwraca (i cache'uje) klienta Gemini dla danego klucza API.

    Klient inicjalizuje wewnętrzną pulę HTTP — tworzenie go przy każdym
    wywołaniu call_gemini() jest kosztowne i wyczerpuje połączenia.
    """
    return _genai.Client(api_key=api_key)

# Wzorzec do wyciągnięcia liczby sekund z komunikatu API (np. "retry in 18.8s")
_RETRY_DELAY_RE = re.compile(r"retry[^\d]*(\d+(?:\.\d+)?)\s*s", re.IGNORECASE)


class _GeminiGenerateResponse(Protocol):
    text: str | None


class _GeminiModelsAPI(Protocol):
    def generate_content(self, *, model: str, contents: str) -> _GeminiGenerateResponse:
        ...


def _parse_retry_delay(error: Exception) -> float | None:
    """Wyciąga sugerowany czas oczekiwania z błędu 429, jeśli jest dostępny."""
    msg = str(error)
    m = _RETRY_DELAY_RE.search(msg)
    if m:
        return float(m.group(1))
    # google-genai może udostępniać retry_delay bezpośrednio na obiekcie błędu
    delay = getattr(error, "retry_delay", None)
    if delay is not None:
        return float(delay)
    return None


def _is_daily_quota(error: Exception) -> bool:
    """Zwraca True gdy to wyczerpany dzienny limit (retry nie pomoże)."""
    return "PerDay" in str(error)


def call_gemini(
    prompt: str,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_retries: int = DEFAULT_RETRIES,
) -> str:
    """
    Wysyła prompt do Gemini i zwraca odpowiedź jako string.

    Przy błędzie 429 (rate-limit) czeka sugerowany czas i ponawia próbę
    (do max_retries razy). Dzienny limit quota nie jest ponawiany.

    Args:
        prompt:      Gotowy prompt tekstowy.
        model:       Identyfikator modelu (domyślnie gemini-2.0-flash).
        api_key:     Klucz API; jeśli None, odczytywany z GEMINI_API_KEY.
        max_retries: Maks. liczba ponowień przy rate-limit (domyślnie 3).

    Returns:
        Tekst odpowiedzi modelu.

    Raises:
        ValueError:                  Brak klucza API.
        google.genai.errors.APIError: Nieodwracalny błąd API.
    """
    key = api_key or os.getenv(_ENV_KEY)
    if not key:
        raise ValueError(
            f"Brak klucza Gemini API. "
            f"Ustaw zmienną środowiskową {_ENV_KEY} lub przekaż api_key."
        )

    client  = _get_client(key)
    attempt = 0

    while True:
        try:
            models_api = cast(_GeminiModelsAPI, client.models)
            response = models_api.generate_content(model=model, contents=prompt)
            text = response.text
            if text is None:
                raise RuntimeError("Gemini zwrocil pusta odpowiedz tekstowa.")
            return text

        except _genai_errors.ClientError as exc:
            if exc.code != 429:
                raise

            if _is_daily_quota(exc):
                raise RuntimeError(
                    f"Dzienny limit zapytań dla modelu {model} wyczerpany. "
                    f"Sprawdź plan i billing: https://ai.dev/rate-limit\n"
                    f"Szczegóły API: {exc}"
                ) from exc

            attempt += 1
            if attempt > max_retries:
                raise RuntimeError(
                    f"Rate-limit po {max_retries} próbach. Spróbuj później."
                ) from exc

            delay = _parse_retry_delay(exc) or (2 ** attempt * 5)
            print(
                f"[warn] 429 rate-limit — czekam {delay:.0f}s "
                f"(próba {attempt}/{max_retries})...",
                file=sys.stderr,
            )
            time.sleep(delay)
