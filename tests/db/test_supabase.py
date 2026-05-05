"""
Supabase database connection + schema validation test.
Uses DATABASE_URL from .env (Supabase pooler, IPv4-compatible).

Pooler: aws-1-ap-northeast-2.pooler.supabase.com
  Transaction pooler port: 6543
  Session pooler port:     5433

Run: python tests/db/test_supabase.py
"""
import asyncio
import asyncpg
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = os.getenv("DATABASE_URL", "")

REQUIRED_TABLES = [
    "ten_k_chunks",
    "transcript_chunks",
    "sessions",
    "messages",
    "semantic_cache",
    "eval_logs",
    "users",
]


async def test_supabase_connection() -> bool:
    if not SUPABASE_URL:
        print("FAIL: DATABASE_URL not set in .env")
        return False

    host = SUPABASE_URL.split("@")[1].split(":")[0] if "@" in SUPABASE_URL else "unknown"
    print("=" * 70)
    print("SUPABASE DATABASE CONNECTION TEST")
    print("=" * 70)
    print(f"Host: {host}")
    print("Note: Transaction pooler (IPv4-compatible, port 6543)")
    print("=" * 70)

    try:
        print("\n[>] Connecting to Supabase...")
        conn = await asyncpg.connect(SUPABASE_URL, timeout=15, statement_cache_size=0)
        print("[OK] Connected!")

        version = await conn.fetchval("SELECT version();")
        print(f"[i]  PostgreSQL: {version[:60]}...")

        current_db = await conn.fetchval("SELECT current_database();")
        print(f"[i]  Database: {current_db}")

        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        found = [r["table_name"] for r in rows]
        print(f"\n[i]  Tables ({len(found)}): {found}")

        missing = [t for t in REQUIRED_TABLES if t not in found]
        if missing:
            print(f"\n[!]  Missing required tables: {missing}")
            print("     Run migration: python db/migrations/001_railway_to_supabase.py")
        else:
            print("[OK] All required tables present")
            print("\n[i]  Row counts:")
            for table in ["ten_k_chunks", "transcript_chunks", "sessions", "messages", "semantic_cache"]:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"     {table}: {count:,}")

        # pgvector check
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("\n[OK] pgvector extension available")
        except Exception as e:
            print(f"\n[!]  pgvector: {e}")

        await conn.close()
        print("\n" + "=" * 70)
        if missing:
            print("[!]  Supabase reachable but migration needed")
        else:
            print("[OK] Supabase fully ready")
        print("=" * 70)
        return len(missing) == 0

    except asyncio.TimeoutError:
        print(f"\n[FAIL] TimeoutError: Supabase pooler unreachable (host={host})")
        print("       Check: https://supabase.com/dashboard")
    except Exception as e:
        print(f"\n[FAIL] {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("[FAIL] Supabase connection FAILED")
    print("=" * 70)
    return False


if __name__ == "__main__":
    result = asyncio.run(test_supabase_connection())
    exit(0 if result else 1)
