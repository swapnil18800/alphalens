"""
Run this FIRST — applies db/schema.sql to your Supabase PostgreSQL.
Usage: python db/setup_db.py
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import asyncpg

load_dotenv()

SCHEMA_FILE = Path(__file__).parent / "schema.sql"


async def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set in .env")
        return

    print(f"Connecting to database…")
    conn = await asyncpg.connect(url, command_timeout=60, statement_cache_size=0)

    sql = SCHEMA_FILE.read_text()
    print(f"Applying schema from {SCHEMA_FILE}…")

    # Remove SQL comments (lines starting with --)
    lines = sql.split("\n")
    cleaned_lines = [line.split("--")[0] for line in lines]  # Remove inline comments
    cleaned_sql = "\n".join(cleaned_lines)

    # Execute entire schema as one batch (preserves structure)
    try:
        await conn.execute(cleaned_sql)
        print("✓ Schema applied successfully")
    except Exception as e:
        print(f"  ERROR applying schema: {e}")
        await conn.close()
        return

    # Verify tables
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    )
    print("\nTables in DB:")
    for t in tables:
        print(f"  ✓ {t['table_name']}")

    await conn.close()
    print("\nDB setup complete.")


if __name__ == "__main__":
    asyncio.run(main())
