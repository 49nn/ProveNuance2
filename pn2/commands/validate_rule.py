"""Komenda: pn2 validate-rule — waliduje regułę Horn względem manifestu predykatów."""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys

from rich import box
from rich.console import Console
from rich.table import Table

console = Console()

ROOT             = pathlib.Path(__file__).resolve().parent.parent.parent
DEFAULT_MANIFEST = ROOT / "templates-schemas" / "predykaty-manifest.json"
DEFAULT_SCHEMA   = ROOT / "templates-schemas" / "schemat-regula.json"


def run(args: argparse.Namespace) -> None:
    # --- Wczytaj regułę --------------------------------------------------
    rule_path = pathlib.Path(args.rule)
    if not rule_path.exists():
        console.print(f"[red]Brak pliku reguły:[/red] {rule_path}")
        raise SystemExit(1)

    try:
        rule_json = json.loads(rule_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        console.print(f"[red]Błąd parsowania JSON:[/red] {exc}")
        raise SystemExit(1)

    # --- Wczytaj manifest -------------------------------------------------
    manifest_path = pathlib.Path(args.manifest)
    if not manifest_path.exists():
        console.print(f"[red]Brak manifestu predykatów:[/red] {manifest_path}")
        raise SystemExit(1)

    # --- Schemat JSON (opcjonalnie) ---------------------------------------
    schema_json: dict | None = None
    schema_path = pathlib.Path(args.schema)
    if schema_path.exists():
        try:
            schema_json = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            console.print(f"[yellow]Nie można wczytać schematu:[/yellow] {exc}")
    else:
        console.print(
            f"[dim]Schemat JSON nie znaleziony ({schema_path.name}) "
            f"— walidacja schematu pominięta.[/dim]"
        )

    # --- Tekst źródłowy (opcjonalnie) ------------------------------------
    source_text: str | None = None
    if args.source:
        src_path = pathlib.Path(args.source)
        if src_path.exists():
            source_text = src_path.read_text(encoding="utf-8")
        else:
            console.print(
                f"[yellow]Tekst źródłowy nie znaleziony:[/yellow] {src_path}"
            )

    # --- Walidacja -------------------------------------------------------
    from validator import ManifestIndex, RuleValidator

    index     = ManifestIndex.from_file(manifest_path)
    validator = RuleValidator(index, schema_json)
    report    = validator.validate(rule_json, source_text)

    rule_id = rule_json.get("id", "?")

    # --- Wynik na konsoli ------------------------------------------------
    if report.is_valid:
        console.print(
            f"[green]OK[/green]  Reguła [bold]{rule_id}[/bold] jest poprawna."
        )
    else:
        console.print(
            f"[red]BŁĄD[/red]  Reguła [bold]{rule_id}[/bold] — "
            f"{len(report.errors)} błąd(ów)."
        )

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Kod",      style="yellow", no_wrap=True)
        table.add_column("Ścieżka", style="cyan",   no_wrap=True)
        table.add_column("Komunikat")
        table.add_column("Poprawka", style="dim")

        for e in report.errors:
            table.add_row(e.code, e.path, e.message, e.expected_fix)

        console.print(table)

    if report.warnings:
        console.print("[yellow]Ostrzeżenia:[/yellow]")
        for w in report.warnings:
            console.print(f"  [yellow]·[/yellow] {w}")

    # --- Wyjście JSON (opcjonalnie) --------------------------------------
    if args.json_output:
        out: dict = {
            "is_valid": report.is_valid,
            "errors": [dataclasses.asdict(e) for e in report.errors],
            "warnings": report.warnings,
        }
        if args.include_normalized and report.normalized_rule is not None:
            out["normalized_rule"] = report.normalized_rule
        print(json.dumps(out, ensure_ascii=False, indent=2))

    if not report.is_valid:
        sys.exit(1)


def add_parser(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "validate-rule",
        help="Waliduje regułę Horn (JSON) względem manifestu predykatów.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=f"""\
Waliduje plik JSON z regułą Horn (etapy A–F):

  A  JSON Schema           (schemat-regula.json, wymaga jsonschema>=4.0)
  B  Predykaty i arność    (whitelist, arność, allowed_in)
  C  Wartości enumów       (value_domain)
  D  Safety Datalog        (range restriction, NAF safety, nazewnictwo zmiennych)
  E  Provenance            (unit niepuste, quote niepuste, quote w tekście źródłowym)
  F  Założenia             (ScopedAssumption: referencje, CWA wymuszenie)

Domyślny manifest predykatów: {DEFAULT_MANIFEST}
Domyślny schemat JSON:        {DEFAULT_SCHEMA}

Przykłady:
  pn2 validate-rule reguła.json
  pn2 validate-rule reguła.json --source regulamin.txt
  pn2 validate-rule reguła.json --json-output --include-normalized
  pn2 validate-rule reguła.json --manifest inny-manifest.json
        """,
    )
    p.add_argument(
        "rule",
        metavar="PLIK_REGUŁY",
        help="Ścieżka do pliku JSON zawierającego regułę Horn.",
    )
    p.add_argument(
        "--manifest", "-m",
        default=str(DEFAULT_MANIFEST),
        metavar="PLIK",
        help=f"Manifest predykatów (domyślnie: {DEFAULT_MANIFEST.name}).",
    )
    p.add_argument(
        "--schema", "-s",
        default=str(DEFAULT_SCHEMA),
        metavar="PLIK",
        help=f"Schemat JSON reguły (domyślnie: {DEFAULT_SCHEMA.name}).",
    )
    p.add_argument(
        "--source",
        default=None,
        metavar="PLIK",
        help="Plik z tekstem źródłowym — do walidacji provenance.quote.",
    )
    p.add_argument(
        "--json-output",
        action="store_true",
        help="Wypisz raport walidacji jako JSON na stdout.",
    )
    p.add_argument(
        "--include-normalized",
        action="store_true",
        help="Dołącz znormalizowaną regułę do wyjścia JSON (wymaga --json-output).",
    )
    p.set_defaults(func=run)
