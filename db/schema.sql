-- =============================================================================
-- schema.sql — schemat tabel dla predykatów ProveNuance2
-- Mapowanie: data_model/predicates.py → PostgreSQL
-- Idempotentny (bezpieczny do wielokrotnego wywołania)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Typy wyliczeniowe (enum)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    CREATE TYPE predicate_io AS ENUM ('input', 'derived', 'both');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE predicate_kind AS ENUM (
        'domain', 'condition', 'decision', 'ui', 'audit', 'builtin'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ---------------------------------------------------------------------------
-- manifest_policy
-- Mapowanie: policy { whitelist_mode, naf_closed_world_predicates }
-- Tabela jednowierszowa (id = 1).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS manifest_policy (
    id                          integer PRIMARY KEY DEFAULT 1,
    whitelist_mode              text    NOT NULL DEFAULT 'allow_only_listed',
    naf_closed_world_predicates text[]  NOT NULL DEFAULT '{}',
    CONSTRAINT single_row CHECK (id = 1)
);

-- ---------------------------------------------------------------------------
-- predicate
-- Mapowanie: PredicateSpec (data_model/predicates.py)
--
-- Kolumny:
--   name, arity, pred            → pola identyfikujące
--   signature                    → list[ArgType] jako text[]
--   io                           → PredicateIO (enum)
--   kind                         → PredicateKind (enum)
--   meaning_pl                   → opis po polsku
--   allowed_in_head / body /
--     negated_body               → AllowedIn (embedded booleans)
--   value_domain_enum_arg_index,
--     value_domain_allowed_values → ValueDomain (embedded, nullable)
--   notes                        → uwagi
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS predicate (
    name                        text            PRIMARY KEY,
    arity                       integer         NOT NULL,
    pred                        text            NOT NULL UNIQUE,
    signature                   text[]          NOT NULL,
    io                          predicate_io    NOT NULL,
    kind                        predicate_kind  NOT NULL,
    meaning_pl                  text,

    -- AllowedIn (embedded)
    allowed_in_head             boolean         NOT NULL DEFAULT true,
    allowed_in_body             boolean         NOT NULL DEFAULT true,
    allowed_in_negated_body     boolean         NOT NULL DEFAULT false,

    -- ValueDomain (embedded, nullable gdy brak ograniczeń)
    value_domain_enum_arg_index integer,
    value_domain_allowed_values text[],

    notes                       text,

    CONSTRAINT arity_range
        CHECK (arity BETWEEN 1 AND 16),
    CONSTRAINT signature_length_matches_arity
        CHECK (cardinality(signature) = arity),
    CONSTRAINT value_domain_arg_index_positive
        CHECK (value_domain_enum_arg_index IS NULL
               OR value_domain_enum_arg_index >= 1),
    CONSTRAINT value_domain_consistent
        CHECK (
            (value_domain_enum_arg_index IS NULL) =
            (value_domain_allowed_values IS NULL)
        )
);

-- Indeks pomocniczy do filtrowania po io/kind
CREATE INDEX IF NOT EXISTS idx_predicate_io   ON predicate (io);
CREATE INDEX IF NOT EXISTS idx_predicate_kind ON predicate (kind);

-- ---------------------------------------------------------------------------
-- document_span
-- Mapowanie: DocumentSpan (data_model/documents.py)
-- Sekcje dokumentów PDF podzielonych przez pdf/parser.py.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS document_span (
    id          serial  PRIMARY KEY,
    doc_id      text    NOT NULL,   -- identyfikator dokumentu (nazwa pliku / fragment_id)
    unit        text    NOT NULL,   -- np. "3.1(b)"
    title       text    NOT NULL,
    content     text    NOT NULL,
    level       integer NOT NULL,
    parent_unit text,
    page_start  integer NOT NULL,
    page_end    integer NOT NULL,
    UNIQUE (doc_id, unit)
);

CREATE INDEX IF NOT EXISTS idx_span_doc ON document_span (doc_id);
