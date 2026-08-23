import asyncio
import json

import httpx
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings


def mint(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    return jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "type": "access",
            "exp": expire,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


async def main():
    token = mint(
        "40f6e5bc-9a63-4b1e-a6cd-d0d5c8f60f60",
        "",  # placeholder; real ids fetched below
    )
    # fetch the actual user id first
    import asyncpg

    conn = await asyncpg.connect(
        "postgresql://postgres:database@localhost:5432/nexara"
    )
    row = await conn.fetchrow(
        "SELECT id, email FROM users WHERE email = 'nexara.dev@gmail.com'"
    )
    await conn.close()

    token = mint(str(row["id"]), row["email"])
    headers = {"Authorization": f"Bearer {token}"}

    base = "http://127.0.0.1:8000/api/v1"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{base}/conversations/", headers=headers)
        print("GET /conversations/ ->", r.status_code)
        body = r.text
        print(body[:2000])

        r2 = await client.get(f"{base}/users/me", headers=headers)
        print("\nGET /users/me ->", r2.status_code)
        print(r2.text[:500])

        # messages of the known conversation
        conv_id = "8d6cb682-6610-4e39-baef-997f0dd8a615"
        r3 = await client.get(
            f"{base}/messages/{conv_id}", headers=headers
        )
        print(f"\nGET /messages/{conv_id[:8]}... ->", r3.status_code)
        print(r3.text[:1200])


asyncio.run(main())
