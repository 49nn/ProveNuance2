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
    domain                      text            NOT NULL DEFAULT 'generic',

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
        ),
    CONSTRAINT domain_valid
        CHECK (domain IN ('generic', 'e-commerce', 'event'))
);

-- Indeks pomocniczy do filtrowania po io/kind/domain
CREATE INDEX IF NOT EXISTS idx_predicate_io     ON predicate (io);
CREATE INDEX IF NOT EXISTS idx_predicate_kind   ON predicate (kind);
CREATE INDEX IF NOT EXISTS idx_predicate_domain ON predicate (domain);

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

-- ---------------------------------------------------------------------------
-- constant
-- Stałe domenowe odkrywane przez ekstraktor reguł Horn.
--
-- Źródła:
--   1. args w regułach bez prefiksu "?" (np. "confirmed", "auction")
--   2. derived_predicates z arity=0 (np. "is_eligible/0" → value "is_eligible")
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS constant (
    value      text  PRIMARY KEY,
    meaning_pl text,
    domain     text  NOT NULL DEFAULT 'generic',
    notes      text,

    CONSTRAINT constant_domain_valid
        CHECK (domain IN ('generic', 'e-commerce', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_constant_domain ON constant (domain);

-- ---------------------------------------------------------------------------
-- assumption
-- Założenia scoped (ScopedAssumption) odkrywane przez ekstraktor.
--
-- Źródła:
--   rules[*].assumptions          (source_type='rule',      source_id=rule.id)
--   new_conditions[*].assumptions (source_type='condition', source_id=condition.id)
--
-- Unikalność: (fragment_id, source_type, source_id, about_pred, type)
-- Re-ekstrakcja tego samego fragmentu → DO UPDATE (nadpisuje text i indeksy).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS assumption (
    id               serial  PRIMARY KEY,
    fragment_id      text    NOT NULL,
    source_type      text    NOT NULL,       -- 'rule' | 'condition'
    source_id        text    NOT NULL,       -- rule.id lub condition.id
    about_pred       text    NOT NULL,       -- np. "delivery_status/2"
    about_atom_index integer,               -- opcjonalne; 0-based indeks atomu w body
    about_arg_index  integer,               -- opcjonalne; 1-based indeks argumentu w atomie
    about_const      text,                  -- opcjonalne; konkretna stała
    type             text    NOT NULL,
    text             text    NOT NULL,
    domain           text    NOT NULL DEFAULT 'generic',

    UNIQUE (fragment_id, source_type, source_id, about_pred, type),

    CONSTRAINT assumption_source_type_valid
        CHECK (source_type IN ('rule', 'condition')),
    CONSTRAINT assumption_type_valid
        CHECK (type IN (
            'data_contract', 'data_semantics', 'enumeration', 'closed_world',
            'external_computation', 'conflict_resolution', 'missing_predicate'
        )),
    CONSTRAINT assumption_domain_valid
        CHECK (domain IN ('generic', 'e-commerce', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_assumption_fragment   ON assumption (fragment_id);
CREATE INDEX IF NOT EXISTS idx_assumption_about_pred ON assumption (about_pred);
CREATE INDEX IF NOT EXISTS idx_assumption_type       ON assumption (type);
CREATE INDEX IF NOT EXISTS idx_assumption_domain     ON assumption (domain);

-- ---------------------------------------------------------------------------
-- condition
-- Mapowanie: ConditionDefinition (data_model/conditions.py)
-- Warunki nazwane odkrywane przez ekstraktor (new_conditions w wyniku).
--
-- id jest globalnie unikalny (stable snake_case używany w meets_condition/2).
-- Re-ekstrakcja: meaning_pl uzupełniane COALESCE; required/optional nadpisywane.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS condition (
    id              text    PRIMARY KEY,       -- stable snake_case, np. "buyer_active"
    meaning_pl      text    NOT NULL,
    required_facts  jsonb   NOT NULL,          -- list[Atom] jako JSON
    optional_facts  jsonb   NOT NULL DEFAULT '[]',
    prov_unit       text[]  NOT NULL DEFAULT '{}',
    prov_quote      text    NOT NULL DEFAULT '',
    domain          text    NOT NULL DEFAULT 'generic',
    notes           text,

    CONSTRAINT condition_domain_valid
        CHECK (domain IN ('generic', 'e-commerce', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_condition_domain ON condition (domain);

-- ---------------------------------------------------------------------------
-- rule
-- Mapowanie: Rule (data_model/rules.py)
-- Reguły Horna odkrywane przez ekstraktor.
--
-- Unikalność: (fragment_id, rule_id).
-- Re-ekstrakcja tego samego fragmentu → DO UPDATE (nadpisuje head/body/provenance).
-- head_args i body przechowywane jako JSONB (umożliwia zapytania GIN).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rule (
    id          serial  PRIMARY KEY,
    fragment_id text    NOT NULL,
    rule_id     text    NOT NULL,       -- np. "R1", "R-auction-qty-1"
    head_pred   text    NOT NULL,       -- np. "auction"
    head_args   jsonb   NOT NULL,       -- list[str], np. ["?O"]
    body        jsonb   NOT NULL,       -- list[Atom], np. [{"pred":"mode","args":["?O","auction"],"negated":false}]
    prov_unit   text[]  NOT NULL DEFAULT '{}',
    prov_quote  text    NOT NULL DEFAULT '',
    domain      text    NOT NULL DEFAULT 'generic',
    notes       text,

    UNIQUE (fragment_id, rule_id),

    CONSTRAINT rule_domain_valid
        CHECK (domain IN ('generic', 'e-commerce', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_rule_fragment  ON rule (fragment_id);
CREATE INDEX IF NOT EXISTS idx_rule_head_pred ON rule (head_pred);
CREATE INDEX IF NOT EXISTS idx_rule_domain    ON rule (domain);
CREATE INDEX IF NOT EXISTS idx_rule_body_gin  ON rule USING gin (body);
