-- ─────────────────────────────────────────────────────────────────
-- Migration 002 — Anonymous sessions + extended user profile
-- Run on Supabase SQL Editor (one-time)
-- ─────────────────────────────────────────────────────────────────

-- 1. Drop FK on sessions.user_id so we can store anon_<uuid> values
--    that don't reference the users table.
ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_user_id_fkey;

-- 2. Extend the users table to store the profile fields we extract
--    from the Clerk JWT (Google sign-in returns first/last/image).
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS image_url  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ DEFAULT NOW();

-- 3. Index on user_id for fast session listing (no longer covered by FK)
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
