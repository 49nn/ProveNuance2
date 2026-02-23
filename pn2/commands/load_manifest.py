"""Komenda: pn2 load-manifest — ładuje manifest predykatów do bazy danych."""

from __future__ import annotations

import argparse
import json
import pathlib

from rich.console import Console

from pn2._db import get_connection

console = Console()

ROOT             = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = ROOT / "templates-schemas" / "predykaty-manifest.json"

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

    console.print(f"Ładuję manifest: [bold]{path}[/bold]")
    _load(path)
    console.print("[dim]Gotowe.[/dim]")


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "load-manifest",
        help="Ładuje manifest predykatów (JSON) do tabeli predicate.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"""
Wczytuje plik manifestu predykatów i zapisuje do bazy (upsert).
Aktualizuje też politykę (manifest_policy): whitelist_mode i NAF predicates.

Domyślny manifest: {DEFAULT_MANIFEST}

Przykłady:
  pn2 load-manifest
  pn2 load-manifest --manifest ścieżka/do/predykaty-manifest.json
        """,
    )
    p.add_argument(
        "--manifest", "-m",
        default=str(DEFAULT_MANIFEST),
        metavar="PLIK",
        help=f"Ścieżka do pliku manifestu JSON (domyślnie: {DEFAULT_MANIFEST.name}).",
    )
    p.set_defaults(func=run)
