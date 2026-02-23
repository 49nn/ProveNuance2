"""
pn2 — narzędzie CLI dla ProveNuance2.

Użycie:
  pn2 <komenda> [opcje]

Komendy:
  predicates   Listuje predykaty z bazy danych.
"""

from __future__ import annotations

import argparse
import sys

from pn2.commands import predicates as cmd_predicates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pn2",
        description="ProveNuance2 — narzędzie CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version="pn2 0.1.0"
    )

    subparsers = parser.add_subparsers(
        title="komendy",
        metavar="<komenda>",
        dest="command",
    )
    subparsers.required = True

    cmd_predicates.add_parser(subparsers)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
