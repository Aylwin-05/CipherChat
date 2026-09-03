"""Create a private DM between two smoke users (direct DB)."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from sqlalchemy import create_engine, text


def main():

    url = (
        settings.DATABASE_URL
        .replace("+asyncpg", "")
        .replace("+aiosqlite", "")
    )

    engine = create_engine(url)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id FROM users "
                "WHERE email LIKE 'g_%' "
                "ORDER BY email LIMIT 2"
            )
        ).all()

    a, b = str(rows[0][0]), str(rows[1][0])

    cid = str(uuid.uuid4())

    with engine.begin() as conn:

        conn.execute(
            text(
                "INSERT INTO conversations "
                "(id, conversation_type, created_at, updated_at) "
                "VALUES (:i, 'private', now(), now())"
            ),
            {"i": cid},
        )

        for uid in (a, b):

            conn.execute(
                text(
                    "INSERT INTO conversation_participants "
                    "(id, conversation_id, user_id, joined_at, "
                    "is_admin, is_pinned, is_archived) "
                    "VALUES (:p, :c, :u, now(), false, false, false)"
                ),
                {
                    "p": str(uuid.uuid4()),
                    "c": cid,
                    "u": uid,
                },
            )

    engine.dispose()

    print("DM CREATED:", cid)


main()
