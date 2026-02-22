-- Włącz rozszerzenie pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Weryfikacja
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
