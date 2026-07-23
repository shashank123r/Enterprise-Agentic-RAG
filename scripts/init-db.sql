-- ──────────────────────────────────────────────
-- Enterprise RAG Platform — Database Initialization
-- ──────────────────────────────────────────────

-- Enable pgvector extension for hybrid search support
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Create schema for the application
CREATE SCHEMA IF NOT EXISTS rag;

-- Set search path
SET search_path TO rag, public;
