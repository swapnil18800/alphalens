"""
Migration script: Railway (DATABASE_URL_2) -> Supabase (DATABASE_URL)

Steps:
  1. Create schema in Supabase from db/schema.sql
  2. Copy data table-by-table in batches (no pg_get_createtablestmt dependency)
  3. Skip tables with no rows; skip errors per-row

Notes:
  - Supabase uses PgBouncer transaction pooler: statement_cache_size=0 required
  - vector(384) columns are copied as-is (asyncpg handles the type)
  - Run AFTER Railway is confirmed reachable: python tests/db/test_railway.py
"""
import asyncio
import asyncpg
import os
import pathlib
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAILWAY_URL  = os.getenv("DATABASE_URL_2", "")  # source
SUPABASE_URL = os.getenv("DATABASE_URL", "")     # target
SCHEMA_FILE  = pathlib.Path(__file__).parent.parent / "schema.sql"
BATCH_SIZE   = 500  # rows per INSERT batch

# Tables to migrate in order (respect FK dependencies)
TABLES = [
    "ten_k_chunks",
    "transcript_chunks",
    "semantic_cache",
    "eval_logs",
    "users",
    "sessions",
    "messages",
]


async def connect_railway() -> asyncpg.Connection:
    print(f"[>] Connecting to Railway ({RAILWAY_URL.split('@')[1].split(':')[0] if '@' in RAILWAY_URL else '?'})...")
    conn = await asyncpg.connect(RAILWAY_URL, timeout=15)
    print("[OK] Railway connected")
    return conn


async def connect_supabase() -> asyncpg.Connection:
    host = SUPABASE_URL.split("@")[1].split(":")[0] if "@" in SUPABASE_URL else "?"
    print(f"[>] Connecting to Supabase ({host})...")
    # statement_cache_size=0 required for PgBouncer transaction-mode pooler
    conn = await asyncpg.connect(SUPABASE_URL, timeout=15, statement_cache_size=0)
    print("[OK] Supabase connected")
    return conn


async def apply_schema(supabase: asyncpg.Connection):
    """Apply db/schema.sql to Supabase (idempotent — IF NOT EXISTS)."""
    if not SCHEMA_FILE.exists():
        print(f"[!]  schema.sql not found at {SCHEMA_FILE}")
        return
    print(f"\n[>] Applying schema from {SCHEMA_FILE.name}...")
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # Split on semicolons, skip empty statements
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    ok = 0
    for stmt in statements:
        try:
            await supabase.execute(stmt)
            ok += 1
        except Exception as e:
            # Already exists or minor issue — log and continue
            print(f"    [!] {str(e)[:80]}")
    print(f"[OK] Schema applied ({ok}/{len(statements)} statements)")


async def migrate_table(
    railway: asyncpg.Connection,
    supabase: asyncpg.Connection,
    table: str,
) -> dict:
    stats = {"rows_read": 0, "rows_written": 0, "errors": 0}

    # Count rows in source
    try:
        total = await railway.fetchval(f"SELECT COUNT(*) FROM {table}")
    except Exception as e:
        print(f"  [!]  Cannot count {table}: {e}")
        return stats

    if total == 0:
        print(f"  [--] {table}: 0 rows, skipping")
        return stats

    print(f"  [>] {table}: {total:,} rows...")

    # Fetch in batches using cursor
    offset = 0
    while offset < total:
        try:
            rows = await railway.fetch(
                f"SELECT * FROM {table} ORDER BY id LIMIT $1 OFFSET $2",
                BATCH_SIZE, offset
            )
        except Exception as e:
            # Some tables (e.g. sessions/messages) use UUID pk, not id
            try:
                rows = await railway.fetch(
                    f"SELECT * FROM {table} LIMIT $1 OFFSET $2",
                    BATCH_SIZE, offset
                )
            except Exception as e2:
                print(f"  [FAIL] {table} fetch failed: {e2}")
                break

        if not rows:
            break

        stats["rows_read"] += len(rows)
        columns = list(rows[0].keys())
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
        insert_sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
        )

        for row in rows:
            try:
                values = [row[col] for col in columns]
                await supabase.execute(insert_sql, *values)
                stats["rows_written"] += 1
            except Exception as e:
                stats["errors"] += 1
                if stats["errors"] <= 3:
                    print(f"    [!] row error: {str(e)[:80]}")

        offset += len(rows)
        pct = int(100 * offset / total)
        print(f"       {offset:,}/{total:,} ({pct}%)...", end="\r")

    print(f"  [OK] {table}: {stats['rows_written']:,} written, {stats['errors']} errors")
    return stats


async def migrate():
    if not RAILWAY_URL:
        print("[FAIL] DATABASE_URL_2 not set (Railway source)")
        return False
    if not SUPABASE_URL:
        print("[FAIL] DATABASE_URL not set (Supabase target)")
        return False

    print("=" * 70)
    print("MIGRATION: Railway -> Supabase")
    print("=" * 70)

    try:
        railway  = await connect_railway()
        supabase = await connect_supabase()
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return False

    await apply_schema(supabase)

    totals = {"rows_read": 0, "rows_written": 0, "errors": 0}
    print(f"\n[>] Migrating {len(TABLES)} tables...")
    print("-" * 70)
    for table in TABLES:
        stats = await migrate_table(railway, supabase, table)
        for k in totals:
            totals[k] += stats[k]

    await railway.close()
    await supabase.close()

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print(f"  Rows read:    {totals['rows_read']:,}")
    print(f"  Rows written: {totals['rows_written']:,}")
    print(f"  Errors:       {totals['errors']}")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. python tests/db/test_supabase.py   (verify all tables + row counts)")
    print("  2. .venv/Scripts/python evals/qa_eval/run_eval.py --full --input evals/qa_eval/question_v4.txt")
    return totals["errors"] == 0


if __name__ == "__main__":
    print("\n[!]  MIGRATION: Railway -> Supabase")
    print("     Source: DATABASE_URL_2 (Railway)")
    print("     Target: DATABASE_URL   (Supabase)")
    print("     This will INSERT all rows (ON CONFLICT DO NOTHING - safe to re-run)\n")
    confirm = input("Continue? (yes/no): ").strip().lower()
    if confirm == "yes":
        result = asyncio.run(migrate())
        exit(0 if result else 1)
    else:
        print("Cancelled.")
        exit(1)
