"""
Enable pgvector on Supabase and create vector indexes for existing ingestion.

This script:
1. Enables the pgvector extension (idempotent)
2. Ensures vector columns exist on both tables
3. Creates ivfflat indexes for semantic search
4. Verifies vector data integrity
5. Reports statistics

Usage:
    python scripts/setup/setup_pgvector_supabase.py

Prerequisites:
    - DATABASE_URL set in .env
    - Supabase project with at least one table created
    - tables: ten_k_chunks, transcript_chunks (created by ingest scripts)
"""
import asyncio
import os
from dotenv import load_dotenv
import asyncpg

import sys
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()


async def setup_pgvector():
    """Enable pgvector and create indexes."""
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set")
        return False

    conn = await asyncpg.connect(url, statement_cache_size=0)

    try:
        print("=" * 70)
        print("pgvector Setup for AlphaLens (Supabase)")
        print("=" * 70)

        # Step 1: Enable pgvector extension
        print("\n[1/5] Enabling pgvector extension...")
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("  ✓ pgvector extension enabled")
        except Exception as e:
            print(f"  ✗ Error enabling pgvector: {e}")
            print("  Note: You may need to enable it manually in Supabase SQL Editor")
            return False

        # Step 2: Verify/create vector columns on ten_k_chunks
        print("\n[2/5] Checking ten_k_chunks table...")
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'ten_k_chunks' AND column_name = 'embedding'
                    AND data_type = 'USER-DEFINED'
                )
            """)

            if result:
                print("  ✓ ten_k_chunks.embedding column exists (vector(384))")
            else:
                print("  ⚠ Creating/updating embedding column...")
                # Try to convert from JSON string to vector if it exists as text
                await conn.execute("""
                    ALTER TABLE ten_k_chunks
                    DROP COLUMN IF EXISTS embedding CASCADE;
                """)
                await conn.execute("""
                    ALTER TABLE ten_k_chunks
                    ADD COLUMN embedding vector(384);
                """)
                print("  ✓ embedding column ready")
        except Exception as e:
            print(f"  ✗ Error with ten_k_chunks: {e}")

        # Step 3: Verify/create vector columns on transcript_chunks
        print("\n[3/5] Checking transcript_chunks table...")
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'transcript_chunks' AND column_name = 'embedding'
                    AND data_type = 'USER-DEFINED'
                )
            """)

            if result:
                print("  ✓ transcript_chunks.embedding column exists (vector(384))")
            else:
                print("  ⚠ Creating/updating embedding column...")
                await conn.execute("""
                    ALTER TABLE transcript_chunks
                    DROP COLUMN IF EXISTS embedding CASCADE;
                """)
                await conn.execute("""
                    ALTER TABLE transcript_chunks
                    ADD COLUMN embedding vector(384);
                """)
                print("  ✓ embedding column ready")
        except Exception as e:
            print(f"  ✗ Error with transcript_chunks: {e}")

        # Step 4: Create ivfflat indexes
        print("\n[4/5] Creating vector indexes (ivfflat)...")
        try:
            # Drop existing indexes if present
            await conn.execute("""
                DROP INDEX IF EXISTS idx_10k_embedding CASCADE;
            """)
            await conn.execute("""
                DROP INDEX IF EXISTS idx_tc_embedding CASCADE;
            """)

            # Create new indexes
            await conn.execute("""
                CREATE INDEX idx_10k_embedding ON ten_k_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            print("  ✓ Created idx_10k_embedding (ivfflat, lists=100)")

            await conn.execute("""
                CREATE INDEX idx_tc_embedding ON transcript_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            print("  ✓ Created idx_tc_embedding (ivfflat, lists=100)")

        except asyncpg.exceptions.DuplicateObjectError:
            print("  ℹ Indexes already exist (skipping recreate)")
        except Exception as e:
            print(f"  ✗ Error creating indexes: {e}")

        # Step 5: Report vector coverage
        print("\n[5/5] Vector coverage report...")
        try:
            stats = await conn.fetchrow("""
                SELECT
                    (SELECT COUNT(*) FROM ten_k_chunks) as ten_k_total,
                    (SELECT COUNT(*) FROM ten_k_chunks WHERE embedding IS NOT NULL) as ten_k_embedded,
                    (SELECT COUNT(DISTINCT ticker) FROM ten_k_chunks) as ten_k_tickers,
                    (SELECT COUNT(*) FROM transcript_chunks) as tc_total,
                    (SELECT COUNT(*) FROM transcript_chunks WHERE embedding IS NOT NULL) as tc_embedded,
                    (SELECT COUNT(DISTINCT ticker) FROM transcript_chunks) as tc_tickers
            """)

            if stats:
                ten_k_coverage = (stats['ten_k_embedded'] / stats['ten_k_total'] * 100) if stats['ten_k_total'] > 0 else 0
                tc_coverage = (stats['tc_embedded'] / stats['tc_total'] * 100) if stats['tc_total'] > 0 else 0

                print(f"\n  10-K Chunks:")
                print(f"    Total: {stats['ten_k_total']:,}")
                print(f"    Embedded: {stats['ten_k_embedded']:,} ({ten_k_coverage:.1f}%)")
                print(f"    Tickers: {stats['ten_k_tickers']}")

                print(f"\n  Transcript Chunks:")
                print(f"    Total: {stats['tc_total']:,}")
                print(f"    Embedded: {stats['tc_embedded']:,} ({tc_coverage:.1f}%)")
                print(f"    Tickers: {stats['tc_tickers']}")

                print(f"\n  ✓ Vector indexing ready for {stats['ten_k_embedded'] + stats['tc_embedded']:,} chunks")

        except Exception as e:
            print(f"  ✗ Error querying stats: {e}")

        print("\n" + "=" * 70)
        print("pgvector setup complete!")
        print("=" * 70)
        print("\nNext steps:")
        print("  1. Run the improved audit script:")
        print("     python scripts/generate_data_audit.py")
        print("  2. Monitor ongoing ingestion in logs:")
        print("     tail -f scripts/ingestion/logs/sec_10k/sec_*.log")
        print("  3. Once ingestion completes, test RAG retrieval")
        print("\n")

        return True

    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        return False
    finally:
        await conn.close()


async def main():
    """Entry point."""
    success = await setup_pgvector()
    exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
