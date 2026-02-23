"""Połączenie z bazą PostgreSQL — konfiguracja przez zmienne środowiskowe."""

from __future__ import annotations

import os
import psycopg2
import psycopg2.extras


def get_connection() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host     = os.getenv("PGHOST",     "localhost"),
        port     = int(os.getenv("PGPORT", "5433")),
        dbname   = os.getenv("PGDATABASE", "provenuance2"),
        user     = os.getenv("PGUSER",     "provenuance2"),
        password = os.getenv("PGPASSWORD", "provenuance2"),
    )
