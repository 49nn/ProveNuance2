FROM pgvector/pgvector:pg17

LABEL org.opencontainers.image.title="ProveNuance2"
LABEL org.opencontainers.image.description="PostgreSQL 17 + pgvector dla ProveNuance2"

# Inicjalizacyjne skrypty SQL (wykonywane raz przy pierwszym uruchomieniu)
COPY init/ /docker-entrypoint-initdb.d/
