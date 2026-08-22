"""Live probe of restored conversation endpoints against :8000.

Auth: mints a real JWT in-process (same secret/algorithm as the
server) for an existing user, then exercises the HTTP stack.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.services.jwt_service import JWTService

BASE = "http://127.0.0.1:8000/api/v1"


def mint_token() -> tuple[str, str, str | None, str | None]:

    sync_url = (
        settings.DATABASE_URL.replace("+asyncpg", "")
        .replace("+aiosqlite", "")
    )

    engine = create_engine(sync_url)

    with engine.connect() as conn:

        user_row = conn.execute(
            text(
                "SELECT id, email FROM users "
                "WHERE email LIKE 'g_alice%' LIMIT 1"
            )
        ).first()

        assert user_row, "smoke user not found"

        user_id = str(user_row[0])

        email = user_row[1]

        conv_rows = conn.execute(
            text(
                "SELECT c.id, c.conversation_type "
                "FROM conversations c "
                "JOIN conversation_participants p "
                "ON p.conversation_id = c.id "
                "WHERE p.user_id = :uid "
                "ORDER BY CASE c.conversation_type "
                "WHEN 'group' THEN 0 ELSE 1 END, "
                "c.created_at DESC LIMIT 2"
            ),
            {"uid": user_id},
        ).all()

    engine.dispose()

    group_id = next(
        (
            str(row[0])
            for row in conv_rows
            if row[1] == "group"
        ),
        None,
    )

    dm_id = next(
        (
            str(row[0])
            for row in conv_rows
            if row[1] == "private"
        ),
        None,
    )

    jwt = JWTService()

    token = jwt.create_access_token(user_id, email)

    return token, email, group_id, dm_id


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def main():

    token, email, group_id, dm_id = mint_token()

    print("MINTED TOKEN FOR:", email)

    print("GROUP:", group_id, "| DM:", dm_id)

    async with httpx.AsyncClient(timeout=30) as client:

        # 0) Conversation list sanity
        r = await client.get(
            f"{BASE}/conversations/", headers=auth(token)
        )
        print("LIST:", r.status_code)

        if group_id:

            # 1) Group detail (restored endpoint: GET /{id})
            r = await client.get(
                f"{BASE}/conversations/{group_id}",
                headers=auth(token),
            )
            print("GROUP DETAIL:", r.status_code)
            body = json.dumps(r.json(), default=str)
            print("  ", body[:300])

            # 2) Invite-link lifecycle (admin endpoints)
            r = await client.post(
                f"{BASE}/conversations/{group_id}"
                f"/group/invite-link",
                headers=auth(token),
            )
            print("CREATE LINK:", r.status_code,
                  str(r.json())[:140])

            r = await client.get(
                f"{BASE}/conversations/{group_id}"
                f"/group/invite-link",
                headers=auth(token),
            )
            print("GET LINK:", r.status_code,
                  str(r.json())[:140])

            r = await client.delete(
                f"{BASE}/conversations/{group_id}"
                f"/group/invite-link",
                headers=auth(token),
            )
            print("REVOKE LINK:", r.status_code, r.json())

        if dm_id:

            # 3) Settings roundtrip on the DM
            r = await client.patch(
                f"{BASE}/conversations/{dm_id}",
                json={"is_pinned": True},
                headers=auth(token),
            )
            print("PIN:", r.status_code, r.json())

            r = await client.get(
                f"{BASE}/conversations/",
                headers=auth(token),
            )
            rows = r.json()
            first_is_dm = bool(rows) and rows[0]["id"] == dm_id
            dm = next(
                (
                    row
                    for row in rows
                    if row["id"] == dm_id
                ),
                None,
            )
            print(
                "LIST: pinned flag =",
                bool(dm and dm["is_pinned"]),
                "| dm sorted first =",
                first_is_dm,
            )

            r = await client.patch(
                f"{BASE}/conversations/{dm_id}",
                json={"is_pinned": False},
                headers=auth(token),
            )
            print("UNPIN:", r.status_code, r.json())

            # 4) Two-party delete: request then cancel (no wipe)
            r = await client.post(
                f"{BASE}/conversations/{dm_id}"
                f"/delete-request",
                headers=auth(token),
            )
            print("DEL REQ:", r.status_code, r.json())

            r = await client.post(
                f"{BASE}/conversations/{dm_id}"
                f"/delete-cancel",
                headers=auth(token),
            )
            print("DEL CANCEL:", r.status_code, r.json())


asyncio.run(main())
