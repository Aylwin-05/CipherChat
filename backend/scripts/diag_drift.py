import asyncio

import app.models  # noqa: F401  (registers all tables on Base.metadata)
import asyncpg
from app.database.base import Base


async def main():
    raw = await asyncpg.connect(
        "postgresql://postgres:database@localhost:5432/nexara"
    )

    db_tables = {
        r["table_name"]
        for r in await raw.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        )
    }

    total_missing = 0
    for table_name, table in sorted(Base.metadata.tables.items()):
        model_cols = set(table.columns.keys())

        if table_name not in db_tables:
            print(f"\nTABLE {table_name}: MISSING IN DB ENTIRELY")
            total_missing += len(model_cols)
            continue

        db_rows = await raw.fetch(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            """,
            table_name,
        )
        db_cols = {r["column_name"] for r in db_rows}

        missing_in_db = model_cols - db_cols
        missing_in_model = db_cols - model_cols

        if missing_in_db or missing_in_model:
            print(f"\nTABLE {table_name}:")
            if missing_in_db:
                total_missing += len(missing_in_db)
                print("  in MODEL but NOT in DB:", sorted(missing_in_db))
            if missing_in_model:
                print("  in DB but NOT in model:", sorted(missing_in_model))

    print("\nTables in models but not in DB:", sorted(set(Base.metadata.tables.keys()) - db_tables))
    print("Total model-only columns:", total_missing)

    await raw.close()


asyncio.run(main())
