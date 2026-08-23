import asyncio
import json
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
from jose import jwt

from app.core.config import settings


async def main():
    conn = await asyncpg.connect(
        "postgresql://postgres:database@localhost:5432/nexara"
    )
    row = await conn.fetchrow(
        "SELECT id, email FROM users WHERE email = 'nexara.dev@gmail.com'"
    )
    await conn.close()

    token = jwt.encode(
        {
            "sub": str(row["id"]),
            "email": row["email"],
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    import websockets

    uri = "ws://127.0.0.1:8000/ws/me"
    subprotocols = [f"nexara.{token}"]

    async with websockets.connect(
        uri, subprotocols=subprotocols, open_timeout=10
    ) as ws:
        # first frame should be "connected" + presence snapshot
        for _ in range(3):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                print("WS EVENT:", data.get("event"), "| keys:", list(data.keys()))
                if data.get("event") == "connected":
                    print("WS CONNECTED OK")
            except asyncio.TimeoutError:
                break

        # simulate a ping
        await ws.send(json.dumps({"event": "ping"}))
        try:
            reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            print("PING ->", reply.get("event"))
        except asyncio.TimeoutError:
            print("PING -> no reply")


asyncio.run(main())
