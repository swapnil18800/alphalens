"""
Railway database connection test.
Uses DATABASE_URL_2 from .env (Railway source DB).
Run: python tests/db/test_railway.py
"""
import asyncio
import asyncpg
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAILWAY_URL = os.getenv("DATABASE_URL_2", "")

REQUIRED_TABLES = [
    "ten_k_chunks",
    "transcript_chunks",
    "sessions",
    "messages",
    "semantic_cache",
    "eval_logs",
    "users",
]


async def test_railway_connection() -> bool:
    if not RAILWAY_URL:
        print("FAIL: DATABASE_URL_2 not set in .env")
        return False

    host = RAILWAY_URL.split("@")[1].split(":")[0] if "@" in RAILWAY_URL else "unknown"
    print("=" * 70)
    print("RAILWAY DATABASE CONNECTION TEST")
    print("=" * 70)
    print(f"Host: {host}")
    print("=" * 70)

    try:
        print("\n[>] Connecting to Railway...")
        conn = await asyncpg.connect(RAILWAY_URL, timeout=15)
        print("[OK] Connected!")

        version = await conn.fetchval("SELECT version();")
        print(f"[i]  PostgreSQL: {version[:60]}...")

        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        found = [r["table_name"] for r in rows]
        print(f"\n[i]  Tables ({len(found)}): {found}")

        missing = [t for t in REQUIRED_TABLES if t not in found]
        if missing:
            print(f"[!]  Missing expected tables: {missing}")
        else:
            print("[OK] All required tables present")

        print("\n[i]  Row counts:")
        for table in ["ten_k_chunks", "transcript_chunks", "sessions", "messages", "semantic_cache"]:
            if table in found:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                print(f"     {table}: {count:,}")

        await conn.close()
        print("\n" + "=" * 70)
        print("[OK] Railway connection SUCCESS")
        print("=" * 70)
        return True

    except asyncio.TimeoutError:
        print(f"\n[FAIL] TimeoutError: Railway proxy unreachable (host={host})")
        print("       Railway may be down. Check: https://status.railway.app")
    except Exception as e:
        print(f"\n[FAIL] {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("[FAIL] Railway connection FAILED")
    print("=" * 70)
    return False


if __name__ == "__main__":
    result = asyncio.run(test_railway_connection())
    exit(0 if result else 1)
