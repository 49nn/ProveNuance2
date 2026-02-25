"""Komenda: pn2 load-manifest — ładuje manifest predykatów (i reguł) do bazy danych."""

from __future__ import annotations

import argparse
import json
import pathlib

from rich.console import Console

from pn2._db import get_connection

console = Console()

ROOT                   = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST       = ROOT / "templates-schemas" / "predykaty-manifest.json"
DEFAULT_RULES_MANIFEST = ROOT / "templates-schemas" / "reguly-manifest.json"

_UPSERT_PREDICATE = """
    INSERT INTO predicate (
        name, arity, pred, signature, io, kind,
        meaning_pl, domain,
        allowed_in_head, allowed_in_body, allowed_in_negated_body,
        value_domain_enum_arg_index, value_domain_allowed_values,
        notes
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (name) DO UPDATE SET
        arity                       = EXCLUDED.arity,
        pred                        = EXCLUDED.pred,
        signature                   = EXCLUDED.signature,
        io                          = EXCLUDED.io,
        kind                        = EXCLUDED.kind,
        meaning_pl                  = EXCLUDED.meaning_pl,
        domain                      = EXCLUDED.domain,
        allowed_in_head             = EXCLUDED.allowed_in_head,
        allowed_in_body             = EXCLUDED.allowed_in_body,
        allowed_in_negated_body     = EXCLUDED.allowed_in_negated_body,
        value_domain_enum_arg_index = EXCLUDED.value_domain_enum_arg_index,
        value_domain_allowed_values = EXCLUDED.value_domain_allowed_values,
        notes                       = EXCLUDED.notes
"""

_UPSERT_POLICY = """
    INSERT INTO manifest_policy (id, whitelist_mode, naf_closed_world_predicates)
    VALUES (1, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        whitelist_mode              = EXCLUDED.whitelist_mode,
        naf_closed_world_predicates = EXCLUDED.naf_closed_world_predicates
"""


_UPSERT_RULE = """
    INSERT INTO rule (
        fragment_id, rule_id,
        head_pred, head_args, body,
        prov_unit, prov_quote,
        domain, notes
    )
    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)
    ON CONFLICT (fragment_id, rule_id) DO UPDATE SET
        head_pred  = EXCLUDED.head_pred,
        head_args  = EXCLUDED.head_args,
        body       = EXCLUDED.body,
        prov_unit  = EXCLUDED.prov_unit,
        prov_quote = EXCLUDED.prov_quote,
        notes      = EXCLUDED.notes
"""

_FRAGMENT_ID_MANIFEST = "__manifest__"


def _normalize_arg(arg) -> str:
    """Konwertuje argument z manifestu do formatu Datalog używanego w bazie.

    Reguła: zmienne pisane z wielkiej litery lub zaczynające się od '_' → prefix '?'.
    Liczby → string. Stałe (małe litery) → bez zmian.
    """
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str) and arg and (arg[0].isupper() or arg[0] == "_"):
        return f"?{arg}"
    return arg if isinstance(arg, str) else str(arg)


def _normalize_atom(atom: dict) -> dict:
    return {
        "pred":    atom["pred"],
        "args":    [_normalize_arg(a) for a in atom.get("args", [])],
        "negated": atom.get("negated", False),
    }


def _load_rules(path: pathlib.Path, conn) -> None:
    """Ładuje reguły z manifestu reguł do tabeli rule."""
    raw   = json.loads(path.read_text(encoding="utf-8"))
    rules = raw.get("rules", [])

    inserted = updated = 0

    with conn.cursor() as cur:
        for r in rules:
            rule_id  = r["rule_id"]
            domain   = r.get("domain", "generic")
            head     = r.get("head", {})
            head_pred = head.get("pred", "")
            head_args = [_normalize_arg(a) for a in head.get("args", [])]
            body      = [_normalize_atom(a) for a in r.get("body", [])]
            notes     = r.get("description_pl") or r.get("kind")

            cur.execute(
                _UPSERT_RULE,
                (
                    _FRAGMENT_ID_MANIFEST, rule_id,
                    head_pred,
                    json.dumps(head_args, ensure_ascii=False),
                    json.dumps(body, ensure_ascii=False),
                    [],   # prov_unit
                    "",   # prov_quote
                    domain,
                    notes,
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1

    console.print(
        f"[green]Reguły:[/green] {inserted} nowych, {updated} zaktualizowanych"
        f"  (łącznie {len(rules)})."
    )


def _load(path: pathlib.Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    predicates = raw.get("predicates", [])
    policy     = raw.get("policy", {})

    try:
        conn = get_connection()
    except Exception as e:
        console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
        raise SystemExit(1)

    inserted = updated = 0

    with conn, conn.cursor() as cur:
        # --- polityka ---
        if policy:
            cur.execute(
                _UPSERT_POLICY,
                (
                    policy.get("whitelist_mode", "allow_only_listed"),
                    policy.get("naf_closed_world_predicates", []),
                ),
            )
            console.print("[green]Polityka manifestu zaktualizowana.[/green]")

        # --- predykaty ---
        for p in predicates:
            allowed = p.get("allowed_in", {})
            vd      = p.get("value_domain") or {}

            cur.execute(
                _UPSERT_PREDICATE,
                (
                    p["name"],
                    p["arity"],
                    p.get("pred") or f"{p['name']}/{p['arity']}",
                    p["signature"],
                    p["io"],
                    p["kind"],
                    p.get("meaning_pl"),
                    p.get("domain", "generic"),
                    allowed.get("head", True),
                    allowed.get("body", True),
                    allowed.get("negated_body", False),
                    vd.get("enum_arg_index"),
                    vd.get("allowed_values") or None,
                    p.get("notes"),
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1

    conn.commit()
    conn.close()
    console.print(
        f"[green]Predykaty:[/green] {inserted} nowych, {updated} zaktualizowanych"
        f"  (łącznie {len(predicates)})."
    )


def run(args: argparse.Namespace) -> None:
    path = pathlib.Path(args.manifest)
    if not path.exists():
        console.print(f"[red]Brak pliku manifestu:[/red] {path}")
        raise SystemExit(1)

    console.print(f"Ładuję manifest predykatów: [bold]{path}[/bold]")
    _load(path)

    rules_path = pathlib.Path(args.rules_manifest)
    if rules_path.exists():
        console.print(f"Ładuję manifest reguł: [bold]{rules_path}[/bold]")
        try:
            conn = get_connection()
        except Exception as e:
            console.print(f"[red]Błąd połączenia z bazą:[/red] {e}")
            raise SystemExit(1)
        with conn:
            _load_rules(rules_path, conn)
        conn.close()
    elif args.rules_manifest != str(DEFAULT_RULES_MANIFEST):
        # Podano jawną ścieżkę, ale plik nie istnieje → błąd
        console.print(f"[red]Brak pliku manifestu reguł:[/red] {rules_path}")
        raise SystemExit(1)
    else:
        console.print(
            f"[dim]Manifest reguł nie znaleziony ({rules_path.name}) — pomijam.[/dim]"
        )

    console.print("[dim]Gotowe.[/dim]")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "load-manifest",
        help="Ładuje manifest predykatów i reguł (JSON) do bazy danych.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"""
Wczytuje plik manifestu predykatów i zapisuje do bazy (upsert).
Aktualizuje też politykę (manifest_policy): whitelist_mode i NAF predicates.
Opcjonalnie ładuje wzorcowe reguły Horn z manifestu reguł do tabeli rule.

Domyślny manifest predykatów: {DEFAULT_MANIFEST}
Domyślny manifest reguł:      {DEFAULT_RULES_MANIFEST}

Przykłady:
  pn2 load-manifest
  pn2 load-manifest --manifest ścieżka/do/predykaty-manifest.json
  pn2 load-manifest --rules-manifest ścieżka/do/reguly-manifest.json
  pn2 load-manifest --no-rules
        """,
    )
    p.add_argument(
        "--manifest", "-m",
        default=str(DEFAULT_MANIFEST),
        metavar="PLIK",
        help=f"Ścieżka do manifestu predykatów (domyślnie: {DEFAULT_MANIFEST.name}).",
    )
    p.add_argument(
        "--rules-manifest", "-r",
        default=str(DEFAULT_RULES_MANIFEST),
        metavar="PLIK",
        help=f"Ścieżka do manifestu reguł (domyślnie: {DEFAULT_RULES_MANIFEST.name}).",
    )
    p.set_defaults(func=run)
