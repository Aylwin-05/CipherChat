"""
LIVE smoke test for the recovery re-issue flow (dev only).

Boots nothing — talks to the RUNNING dev backend on :8000 and
the DEV PostgreSQL database. Creates a throwaway account via a
DB-inserted OTP (hash known to this script), registers a device
(getting the recovery code), re-requests the code (same secret
re-wrap), and verifies the running server's responses.

Usage:
    cd backend
    python scripts/recover_smoke.py

Requires: uvicorn running on :8000, PostgreSQL up, .env loaded.
"""

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.database.database import AsyncSessionLocal
from app.models.otp import OTPCode
from app.utils.security import SecurityUtils

from tests.test_recovery_reissue import make_key_material

BASE = "http://localhost:8000/api/v1"
EMAIL = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
OTP = "123456"


async def seed_otp(session):
    session.add(
        OTPCode(
            email=EMAIL,
            otp_hash=SecurityUtils.hash_otp(OTP),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )
    await session.commit()
    print(f"[seed] OTP row for {EMAIL}")


async def main():
    async with AsyncSessionLocal() as session:
        await seed_otp(session)

    async with httpx.AsyncClient(base_url=BASE, timeout=20) as client:

        r = await client.post(
            "/auth/verify-otp",
            json={"email": EMAIL, "otp": OTP},
        )
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[1] OTP login OK")

        r = await client.post(
            "/devices/register",
            json={
                "device_id": f"smoke-{uuid.uuid4().hex[:8]}",
                "platform": "web",
                "device_name": "Smoke Test",
                **make_key_material(),
            },
            headers=headers,
        )
        assert r.status_code == 200, r.text
        device = r.json()
        assert device["recovery_code"], "recovery code minted"
        print(f"[2] device registered, recovery code: {device['recovery_code']}")

        from app.services.recovery_service import unlock_sync_secret

        secret = unlock_sync_secret(
            device["recovery_code"].replace("-", ""),
            device["recovery_salt"],
            device["recovery_wrapped_key"],
        )
        assert secret, "code unlocks the secret"
        print("[3] original code unlocks the sync secret")

        r = await client.post(
            "/recovery/request",
            json={"secret_b64": secret},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["mode"] == "same_secret", data
        assert data["remaining"] == 2, data
        print(f"[4] re-issue requested: mode={data['mode']} remaining={data['remaining']}")

        r = await client.get("/recovery/unlock", headers=headers)
        current = r.json()
        assert unlock_sync_secret(
            device["recovery_code"].replace("-", ""),
            current["salt"],
            current["wrapped_key"],
        ) is None, "old code no longer matches the served material"
        print("[5] old code rejected against the new salt (expected)")

        r = await client.post("/recovery/request", json={}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "new_secret", r.json()
        print("[6] no-secret request mints a fresh key (expected)")

        r = await client.post("/recovery/request", json={}, headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["remaining"] == 0, r.json()
        print("[7] third request still allowed, remaining=0 (expected)")

        r = await client.post("/recovery/request", json={}, headers=headers)
        assert r.status_code == 429, r.text
        print(f"[8] rate limit hit: 429 with Retry-After={r.headers.get('retry-after')}")

        r = await client.post(
            "/recovery/verify",
            json={"token": "garbage-token-xyz", "email": EMAIL, "otp": OTP},
        )
        assert r.status_code == 404, r.text
        print("[9] bogus token -> 404")

        print("\nALL LIVE SMOKE CHECKS PASSED")


if __name__ == "__main__":
    asyncio.run(main())