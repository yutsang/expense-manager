-- Extensions enabled once at DB-init time.
-- Alembic migrations must NOT re-create these.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- trigram search on descriptions/names

-- Separate test database (used by testcontainers / CI)
CREATE DATABASE aegis_test WITH OWNER aegis;
