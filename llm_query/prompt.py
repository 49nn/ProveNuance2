"""
llm_query/prompt.py — budowanie promptu dla ekstraktora reguł Horn.

Funkcje publiczne:
  fetch_predicates(domain)           -> list[str]
  fetch_predicates_for_nlp(domain)   -> list[dict]
  fetch_constants(domain)            -> list[str]
  read_conditions(path | None)       -> str
  read_fragment(path | None)         -> str
  build_prompt(domain, conditions, fragment, template_path) -> str
"""

from __future__ import annotations

import json
import pathlib
import sys

from pn2._db import get_connection

ROOT          = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates-schemas" / "prompt-extractor.md"

_EMPTY_CONDITIONS = "{}"
_EMPTY_FRAGMENT   = "[WKLEJ TU FRAGMENT]"


def fetch_predicates(domain: str) -> list[str]:
    """
    Zwraca listę pred (name/arity) dla danej domeny.
    Zawsze dołączane: predykaty domain='generic' (w tym builtin).
    Dodatkowo: predykaty domain=<domain> (jeśli różny od 'generic').
    Zawiera UNION z derived_predicate — predykaty odkryte automatycznie
    przez ekstraktor są widoczne w kolejnych ekstrakcjach.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if domain == "generic":
                cur.execute(
                    """
                    SELECT pred FROM predicate
                    WHERE domain = 'generic'
                    UNION
                    SELECT pred FROM derived_predicate
                    WHERE domain = 'generic'
                    ORDER BY pred
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT pred FROM predicate
                    WHERE domain = 'generic' OR domain = %s
                    UNION
                    SELECT pred FROM derived_predicate
                    WHERE domain = 'generic' OR domain = %s
                    ORDER BY pred
                    """,
                    (domain, domain),
                )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def fetch_predicates_for_nlp(domain: str) -> list[dict]:
    """
    Zwraca pełne obiekty predykatów EDB (io != 'derived') dla promptu ekstrakcji NLP.

    Każdy obiekt zawiera: pred, name, arity, signature, meaning_pl
    oraz opcjonalnie value_domain (gdy predykat ma ograniczony zbiór wartości).
    Używane przez nlp-solve do przekazania LLM informacji o dostępnych predykatach.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if domain == "generic":
                cur.execute(
                    """
                    SELECT name, arity, pred, signature, meaning_pl,
                           value_domain_enum_arg_index, value_domain_allowed_values
                    FROM predicate
                    WHERE domain = 'generic' AND io != 'derived'
                    ORDER BY kind, name
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT name, arity, pred, signature, meaning_pl,
                           value_domain_enum_arg_index, value_domain_allowed_values
                    FROM predicate
                    WHERE (domain = 'generic' OR domain = %s) AND io != 'derived'
                    ORDER BY kind, name
                    """,
                    (domain,),
                )
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for name, arity, pred, signature, meaning_pl, vd_idx, vd_vals in rows:
        entry: dict = {
            "pred": pred,
            "name": name,
            "arity": arity,
            "signature": list(signature) if signature else [],
            "meaning_pl": meaning_pl or "",
        }
        if vd_idx is not None and vd_vals:
            entry["value_domain"] = {
                "arg_index": vd_idx,
                "allowed_values": list(vd_vals),
            }
        result.append(entry)
    return result


def _rule_to_datalog(head_pred: str, head_args: list, body: list) -> str:
    """Formatuje regułę Horn jako napis Datalog."""
    def _fmt(pred: str, args: list, negated: bool = False) -> str:
        s = f"{pred}({', '.join(str(a) for a in args)})"
        return (r"\+ " if negated else "") + s

    head = _fmt(head_pred, head_args)
    body_parts = [_fmt(a["pred"], a.get("args", []), a.get("negated", False)) for a in body]
    if body_parts:
        return f"{head} :- {', '.join(body_parts)}."
    return f"{head}."


def fetch_rules(domain: str) -> list[str]:
    """
    Zwraca przykładowe reguły Horn z tabeli rule (z manifestu) jako napisy Datalog.
    Zawsze dołączane: reguły domain='generic'.
    Dodatkowo: reguły domain=<domain> (jeśli różny od 'generic').
    Limit 25 reguł — wyłącznie wzorcowe.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if domain == "generic":
                cur.execute(
                    """
                    SELECT head_pred, head_args, body
                    FROM rule
                    WHERE domain = 'generic'
                    ORDER BY domain, head_pred
                    LIMIT 25
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT head_pred, head_args, body
                    FROM rule
                    WHERE domain = 'generic' OR domain = %s
                    ORDER BY domain, head_pred
                    LIMIT 25
                    """,
                    (domain,),
                )
            rows = cur.fetchall()
    finally:
        conn.close()

    result = []
    for head_pred, head_args, body in rows:
        if not isinstance(head_args, list):
            head_args = json.loads(head_args) if isinstance(head_args, str) else []
        if not isinstance(body, list):
            body = json.loads(body) if isinstance(body, str) else []
        result.append(_rule_to_datalog(head_pred, head_args, body))
    return result


def fetch_constants(domain: str) -> list[str]:
    """
    Zwraca listę znanych stałych dla danej domeny.
    Zawsze dołączane: stałe domain='generic'.
    Dodatkowo: stałe domain=<domain> (jeśli różny od 'generic').
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if domain == "generic":
                cur.execute(
                    "SELECT value FROM constant WHERE domain = 'generic' ORDER BY value"
                )
            else:
                cur.execute(
                    """
                    SELECT value FROM constant
                    WHERE domain = 'generic' OR domain = %s
                    ORDER BY value
                    """,
                    (domain,),
                )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def read_conditions(path: str | None) -> str:
    """Wczytuje słownik warunków z pliku JSON lub zwraca pusty obiekt."""
    if path is None:
        return _EMPTY_CONDITIONS
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[warn] Plik warunków nie istnieje: {p}", file=sys.stderr)
        return _EMPTY_CONDITIONS
    return p.read_text(encoding="utf-8").strip()


def read_fragment(path: str | None) -> str:
    """Wczytuje fragment regulaminu z pliku tekstowego lub zwraca placeholder."""
    if path is None:
        return _EMPTY_FRAGMENT
    p = pathlib.Path(path)
    if not p.exists():
        print(f"[warn] Plik fragmentu nie istnieje: {p}", file=sys.stderr)
        return _EMPTY_FRAGMENT
    return p.read_text(encoding="utf-8").strip()


def _load_template(template_path: pathlib.Path) -> str:
    """Wczytuje szablon i usuwa otoczkę ```text / ```."""
    body = template_path.read_text(encoding="utf-8").strip()
    if body.startswith("```text"):
        body = body[len("```text"):].lstrip("\n")
    if body.endswith("```"):
        body = body[: body.rfind("```")].rstrip()
    return body


def build_prompt(
    domain: str,
    conditions: str,
    fragment: str,
    template_path: pathlib.Path = TEMPLATE_PATH,
    no_negation: bool = False,
) -> str:
    """
    Buduje gotowy prompt zastępując wszystkie placeholdery.

    Args:
        domain:        Nazwa domeny (generic / e-commerce / event).
        conditions:    Zawartość słownika warunków jako string JSON.
        fragment:      Tekst fragmentu regulaminu.
        template_path: Ścieżka do szablonu prompt-extractor.md.
        no_negation:   Gdy True, zakazuje LLM używania negacji (negated: true).

    Returns:
        Wypełniony prompt gotowy do wysłania do modelu.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Brak pliku szablonu: {template_path}")

    predicates      = fetch_predicates(domain)
    allowed_json    = json.dumps(predicates, ensure_ascii=False, indent=2)
    constants       = fetch_constants(domain)
    constants_json  = json.dumps(constants, ensure_ascii=False, indent=2)
    example_rules   = fetch_rules(domain)
    example_rules_txt = (
        "\n".join(example_rules) if example_rules else "(brak wzorcowych reguł w bazie)"
    )
    body            = _load_template(template_path)

    result = (
        body
        .replace("{{DOMAIN}}",               domain)
        .replace("{{ALLOWED_PREDICATES}}",    allowed_json)
        .replace("{{KNOWN_CONSTANTS}}",       constants_json)
        .replace("{{EXAMPLE_RULES}}",         example_rules_txt)
        .replace("{{CONDITION_DICTIONARY}}", conditions)
        .replace("{{FRAGMENT}}",              fragment)
    )

    if no_negation:
        # Zastąp zezwolenie na negację zakazem
        result = result.replace(
            '- Negacja w ciele dopuszczalna jako stratified NAF: atom z polem "negated": true.',
            '- ZAKAZ NEGACJI: NIE używaj "negated": true w żadnym atomie ciała.'
            ' Wyjątki modeluj przez odrębne reguły pozytywne (np. denied, excluded, not_eligible).',
        )
        # Dodaj ostrzeżenie tuż przed sekcją TERAZ
        result = result.replace(
            "TERAZ:",
            'WAŻNE — BEZWZGLĘDNY ZAKAZ: żaden atom w żadnej regule nie może mieć'
            ' "negated": true. Każdy wygenerowany atom musi mieć "negated": false lub brak pola "negated".\n\nTERAZ:',
        )

    return result
