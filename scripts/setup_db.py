"""
Run this FIRST — applies db/schema.sql to your Supabase PostgreSQL.
Usage: python scripts/setup_db.py
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import asyncpg

load_dotenv()

SCHEMA_FILE = Path(__file__).parent.parent / "db" / "schema.sql"


async def main():
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set in .env")
        return

    print(f"Connecting to database…")
    conn = await asyncpg.connect(url)

    sql = SCHEMA_FILE.read_text()
    print(f"Applying schema from {SCHEMA_FILE}…")

    # Execute each statement separately
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            try:
                await conn.execute(stmt)
            except Exception as e:
                print(f"  WARN: {e}")

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
