-- AlphaLens — PostgreSQL Schema
-- Run via: python scripts/setup/setup_db.py
-- Or manually: psql $DATABASE_URL -f db/schema.sql
-- Requires pgvector extension (Railway: pre-installed; Supabase: enable in SQL Editor).

-- ── Extensions ───────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── SEC 10-K filing chunks ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ten_k_chunks (
    id           BIGSERIAL   PRIMARY KEY,
    ticker       TEXT        NOT NULL,
    company_name TEXT,
    filing_year  INTEGER,
    section      TEXT,                       -- e.g. "Risk Factors", "MD&A"
    chunk_text   TEXT        NOT NULL,
    embedding    vector(384),                -- all-MiniLM-L6-v2
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_10k_ticker    ON ten_k_chunks (ticker);
CREATE INDEX IF NOT EXISTS idx_10k_year      ON ten_k_chunks (ticker, filing_year);
CREATE INDEX IF NOT EXISTS idx_10k_embedding ON ten_k_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Earnings / quarterly financial chunks (yfinance summaries) ───────────
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id          BIGSERIAL   PRIMARY KEY,
    ticker      TEXT        NOT NULL,
    company_name TEXT,
    year        INTEGER,
    quarter     INTEGER,
    chunk_text  TEXT        NOT NULL,
    embedding   vector(384),
    metadata    JSONB       DEFAULT '{}',   -- source, revenue, net_income, etc.
    chunk_index INTEGER     DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tc_ticker    ON transcript_chunks (ticker);
CREATE INDEX IF NOT EXISTS idx_tc_yq        ON transcript_chunks (year, quarter);
CREATE INDEX IF NOT EXISTS idx_tc_ticker_yq ON transcript_chunks (ticker, year, quarter);
CREATE INDEX IF NOT EXISTS idx_tc_embedding ON transcript_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Semantic cache ────────────────────────────────────────────────────────
-- Stores Q→A pairs; lookup uses cosine similarity ≥ 0.92 to skip full pipeline.
CREATE TABLE IF NOT EXISTS semantic_cache (
    id              BIGSERIAL   PRIMARY KEY,
    question        TEXT        NOT NULL,
    query_embedding vector(384),
    response        TEXT        NOT NULL,
    hit_count       INTEGER     DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_hit_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cache_embedding ON semantic_cache
    USING hnsw (query_embedding vector_cosine_ops);

-- ── Evaluation logs (RAGAS per-query scores) ─────────────────────────────
CREATE TABLE IF NOT EXISTS eval_logs (
    id                  BIGSERIAL   PRIMARY KEY,
    session_id          TEXT,
    question            TEXT        NOT NULL,
    answer              TEXT,
    context_chunks      INTEGER,
    faithfulness_score  FLOAT,
    eval_reason         TEXT,
    llm_provider        TEXT,
    latency_ms          INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_session ON eval_logs (session_id);
CREATE INDEX IF NOT EXISTS idx_eval_created ON eval_logs (created_at);

-- ── Users (synced from Clerk webhooks) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id         TEXT        PRIMARY KEY,     -- Clerk user ID (user_xxxxx)
    email      TEXT        UNIQUE NOT NULL,
    full_name  TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Conversation sessions ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id            UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       TEXT        REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT        DEFAULT 'New Chat',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    message_count INTEGER     DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

-- ── Messages ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID        REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    metadata    JSONB       DEFAULT '{}',  -- citations, confidence, eval_score
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages (session_id, created_at);
