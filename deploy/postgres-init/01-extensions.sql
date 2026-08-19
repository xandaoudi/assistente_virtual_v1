-- Executado UMA ÚNICA VEZ, na primeira criação do volume do banco.
-- Se o volume pgdata já existir, este arquivo é ignorado.

-- Geração de UUID no lado do banco (chaves primárias do modelo de dados).
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Busca textual sem acento — necessária para o RF-15 (buscar eventos por
-- texto) e RF-56 (filtro por texto em transações) funcionarem com
-- "supermercado" encontrando "Supermercado" e "almoco" encontrando "almoço".
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Memória semântica de longo prazo (questão Q-07 do requirements.md).
-- Descomente quando decidir usar embeddings. Requer a imagem pgvector/pgvector
-- no lugar de postgres:16-alpine.
-- CREATE EXTENSION IF NOT EXISTS "vector";
