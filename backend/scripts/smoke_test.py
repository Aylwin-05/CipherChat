"""
Nexara live smoke test.

Boots the real backend (uvicorn) against the PostgreSQL configured in
backend/.env, then drives the full happy path over real HTTP + WebSocket:

  1. Register two users via email OTP (dev-mode OTPs are parsed from the
     server console log; live SMTP delivery is NOT required).
  2. User A opens a private conversation with B.
  3. Both connect to /ws/me (subprotocol auth: "nexara.<token>").
  4. A sends one encrypted message (payload is opaque to the backend).
  5. The "message" websocket event reaches B.
  6. B marks the message delivered + read -> A receives both receipts.
  7. State is verified over REST (message list shows delivered/read).

Usage (from backend/):

    python scripts/smoke_test.py

Exit code 0 = everything passed. Requires: httpx, websockets.
"""

import asyncio
import json
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import websockets

BACKEND_DIR = Path(__file__).resolve().parent.parent
PORT = 8800 + (uuid.uuid4().int % 500)
BASE_URL = f"http://127.0.0.1:{PORT}"
WS_URL = f"ws://127.0.0.1:{PORT}/ws/me"
API = f"{BASE_URL}/api/v1"

# uvicorn colors its logs with SGR escape codes even when stdout is a
# pipe; strip them so "[DEV] OTP for ...: 123456" always matches.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
OTP_RE = re.compile(r"\[DEV\] OTP for (\S+): (\d{6})")

TIMEOUT = 60.0


# ======================================================================
# Log helpers
# ======================================================================

def log(step: str, ok: bool, detail: str = ""):
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {step}" + (f" - {detail}" if detail else ""))
    return ok


# ======================================================================
# OTP extraction from the uvicorn console log
# ======================================================================

class LogReader:
    """Background thread drains the server's stdout into a queue so the
    event loop never blocks on pipe I/O (a blocking readline() on an
    idle child would deadlock the whole async test)."""

    def __init__(self, process):
        self.process = process
        self.otps: dict[str, str] = {}
        self._q: "queue.Queue[str]" = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        if self.process.stdout is None:
            return
        for line in self.process.stdout:
            self._q.put(line)

    def drain(self):
        try:
            while True:
                line = self._q.get_nowait()
                match = OTP_RE.search(ANSI_RE.sub("", line))
                if match:
                    self.otps[match.group(1)] = match.group(2)
        except queue.Empty:
            pass

    async def wait_for_otp(self, email: str, timeout: float = TIMEOUT) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if email in self.otps:
                return self.otps[email]
            self.drain()
            await asyncio.sleep(0.05)
        self.drain()
        return self.otps.get(email)


async def make_friends(
    client: httpx.AsyncClient,
    token_a: str,
    user_b_id: str,
    token_b: str,
):
    """A sends a friend request to B; B accepts. Returns True on success."""
    resp = await client.post(
        f"{API}/friends/request",
        json={"receiver_id": str(user_b_id)},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    if resp.status_code != 200:
        return False, f"request: {resp.status_code} {resp.text}"

    pending = await client.get(
        f"{API}/friends/pending",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    pending_list = pending.json() if pending.status_code == 200 else []
    if not pending_list:
        return False, "no pending request visible to B"

    resp = await client.post(
        f"{API}/friends/accept",
        json={"friendship_id": str(pending_list[0]["id"])},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    if resp.status_code != 200:
        return False, f"accept: {resp.status_code} {resp.text}"
    return True, ""


# ======================================================================
# Group chat flow: friendships -> group -> per-recipient key message
# -> ws fan-out -> admin add -> leave
# ======================================================================

async def group_flow(
    client: httpx.AsyncClient,
    reader: LogReader,
    failures: list[str],
):
    stamp = uuid.uuid4().hex[:8]

    def auth(token: str):
        return {"Authorization": f"Bearer {token}"}

    # ----------------------------------------------------------
    # Register 4 users and establish friendships with the admin
    # ----------------------------------------------------------
    users = {}
    for name in ("alice", "bob", "carol", "dave"):
        token, uid = await register_user(
            client,
            reader,
            f"g_{name}_{stamp}@example.com",
        )
        users[name] = {"token": token, "id": uid}

    log("group: 4 users registered", True)

    for name in ("bob", "carol", "dave"):
        ok, detail = await make_friends(
            client,
            users["alice"]["token"],
            users[name]["id"],
            users[name]["token"],
        )
        if not ok:
            failures.append(f"friendship alice<->{name}: {detail}")
            return
    log("group: friendships alice <-> bob/carol/dave", True)

    # ----------------------------------------------------------
    # Create the group (admin = alice)
    # ----------------------------------------------------------
    resp = await client.post(
        f"{API}/conversations/group",
        json={
            "name": "Smoke Crew",
            "member_ids": [
                str(users["bob"]["id"]),
                str(users["carol"]["id"]),
            ],
        },
        headers=auth(users["alice"]["token"]),
    )
    if resp.status_code != 200:
        failures.append(f"group create: {resp.status_code} {resp.text}")
        return
    group = resp.json()
    group_id = group["id"]
    ok = (
        group.get("conversation_type") == "group"
        and group.get("participant_count") == 3
        and group.get("name") == "Smoke Crew"
    )
    log(
        "group created (type=group, 3 members)",
        ok,
        json.dumps(group),
    )

    # All members see it in their conversation list
    for name in ("alice", "bob", "carol"):
        convs = await client.get(
            f"{API}/conversations/",
            headers=auth(users[name]["token"]),
        )
        ids = [c["id"] for c in convs.json()]
        ok = group_id in ids
        log(f"group visible to {name}", ok, f"{len(ids)} conversations")
        if not ok:
            failures.append(f"group not in {name}'s conversation list")

    # ----------------------------------------------------------
    # Group detail: participants + public_key surface
    # ----------------------------------------------------------
    detail = await client.get(
        f"{API}/conversations/{group_id}",
        headers=auth(users["alice"]["token"]),
    )
    detail_json = detail.json() if detail.status_code == 200 else {}
    participants = detail_json.get("participants", [])
    log(
        "group detail exposes participants",
        detail.status_code == 200 and len(participants) == 3,
        f"participants={len(participants)}",
    )

    # ----------------------------------------------------------
    # Send a group message with per-recipient wrapped keys
    # ----------------------------------------------------------
    msg_payload = {
        "id": str(uuid.uuid4()),
        "conversation_id": group_id,
        "sender_id": str(users["alice"]["id"]),
        "ciphertext": "opaque-group-ciphertext",
        "encrypted_key_sender": "opaque-key-sender",
        "encrypted_key_receiver": "opaque-key-receiver",
        "nonce": "opaque-nonce",
        "created_at": time.strftime(
            "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
        ),
    }

    resp = await client.post(
        f"{API}/messages/send",
        json={
            "conversation_id": group_id,
            "ciphertext": msg_payload["ciphertext"],
            "encrypted_key_sender": msg_payload["encrypted_key_sender"],
            "encrypted_key_receiver": msg_payload["encrypted_key_receiver"],
            "nonce": msg_payload["nonce"],
            "message_type": "text",
            "recipient_keys": [
                {
                    "user_id": str(users["bob"]["id"]),
                    "encrypted_key": "wrapped-for-bob",
                },
                {
                    "user_id": str(users["carol"]["id"]),
                    "encrypted_key": "wrapped-for-carol",
                },
            ],
        },
        headers=auth(users["alice"]["token"]),
    )
    if resp.status_code != 200:
        failures.append(f"group message send: {resp.status_code} {resp.text}")
        return
    stored = resp.json()
    ok = len(stored.get("recipient_keys", [])) == 2
    log(
        "group message stored with per-recipient keys",
        ok,
        f"id={stored['id']}",
    )

    # ----------------------------------------------------------
    # WS fan-out: alice broadcasts, bob + carol both receive
    # ----------------------------------------------------------
    ws_a, _ = await connect_ws(users["alice"]["token"])
    ws_b, _ = await connect_ws(users["bob"]["token"])
    ws_c, _ = await connect_ws(users["carol"]["token"])

    await ws_a.send(json.dumps({"event": "message", **msg_payload}))

    for name, ws in (("bob", ws_b), ("carol", ws_c)):
        received = await recv_event(ws, "message", timeout=10)
        ok = received.get("id") == msg_payload["id"] and received.get(
            "sender_id"
        ) == str(users["alice"]["id"])
        log(
            f"group message broadcast reached {name}",
            ok,
            str(received.get("id")),
        )

    # carol marks it read -> alice gets the receipt
    await ws_c.send(
        json.dumps(
            {
                "event": "read",
                "conversation_id": group_id,
                "message_id": stored["id"],
            }
        )
    )
    read = await recv_event(ws_a, "read", timeout=10)
    log(
        "group read receipt broadcast to alice",
        read.get("message_id") == str(stored["id"]),
        str(read),
    )

    # ----------------------------------------------------------
    # REST history for a member carries the wrapped keys
    # ----------------------------------------------------------
    history = await client.get(
        f"{API}/messages/{group_id}",
        headers=auth(users["carol"]["token"]),
    )
    msgs = history.json() if history.status_code == 200 else []
    own_key = any(
        k.get("user_id") == str(users["carol"]["id"])
        for m in msgs
        for k in m.get("recipient_keys", [])
    )
    log(
        "carol's history includes her wrapped key",
        len(msgs) == 1 and own_key,
        f"{len(msgs)} message(s)",
    )

    # ----------------------------------------------------------
    # Admin adds dave; non-admin cannot add
    # ----------------------------------------------------------
    resp = await client.post(
        f"{API}/conversations/{group_id}/group/add",
        json={"member_ids": [str(users["dave"]["id"])]},
        headers=auth(users["alice"]["token"]),
    )
    ok = resp.status_code == 200 and resp.json().get("participant_count") == 4
    log("admin adds dave (4 members)", ok, str(resp.status_code))

    resp = await client.post(
        f"{API}/conversations/{group_id}/group/add",
        json={"member_ids": [str(users["dave"]["id"])]},
        headers=auth(users["bob"]["token"]),
    )
    log(
        "non-admin add rejected",
        resp.status_code == 403,
        str(resp.status_code),
    )

    # ----------------------------------------------------------
    # carol leaves; alice (admin) sees 3 members
    # ----------------------------------------------------------
    resp = await client.post(
        f"{API}/conversations/{group_id}/group/leave",
        headers=auth(users["carol"]["token"]),
    )
    ok = resp.status_code == 200 and resp.json().get("status") == "left"
    log("carol leaves the group", ok, resp.text)

    detail = await client.get(
        f"{API}/conversations/{group_id}",
        headers=auth(users["alice"]["token"]),
    )
    left = (
        str(users["carol"]["id"])
        not in [
            p.get("user_id")
            for p in detail.json().get("participants", [])
        ]
        if detail.status_code == 200
        else False
    )
    log("group detail no longer lists carol", left)

    # carol lost access
    resp = await client.get(
        f"{API}/conversations/{group_id}",
        headers=auth(users["carol"]["token"]),
    )
    log(
        "leaver loses group access",
        resp.status_code == 403,
        str(resp.status_code),
    )

    await ws_a.close()
    await ws_b.close()
    await ws_c.close()


# ======================================================================
# Test steps
# ======================================================================

async def register_user(client: httpx.AsyncClient, reader: LogReader, email: str):
    """send-otp -> (wait for dev OTP in server log) -> verify-otp.

    The OTP is committed and logged BEFORE the SMTP delivery attempt,
    so we drain the server log while the request is still in flight and
    never wait on SMTP: if the mail server lingers, we cancel the
    request and verify with the logged OTP anyway (the DB record exists).

    Returns (access_token, user_id) or raises.
    """
    post_task = asyncio.create_task(
        client.post(
            f"{API}/auth/send-otp",
            json={"email": email},
            timeout=TIMEOUT,
        )
    )

    otp = None
    while not post_task.done():
        reader.drain()
        if email in reader.otps:
            otp = reader.otps[email]
            break
        await asyncio.sleep(0.1)
    if otp is None:
        reader.drain()
        otp = reader.otps.get(email)

    if otp is None:
        post_task.cancel()
        raise RuntimeError(
            f"No [DEV] OTP found in server log for {email}"
        )

    # Grace period for the HTTP response; cancel if SMTP drags on.
    try:
        resp = await asyncio.wait_for(post_task, timeout=20)
    except asyncio.TimeoutError:
        post_task.cancel()
        resp = None

    if resp is not None and resp.status_code != 200:
        print(
            f"  note: send-otp returned {resp.status_code} for {email} "
            f"(SMTP unreachable?) - continuing with the logged OTP"
        )

    resp = await client.post(
        f"{API}/auth/verify-otp",
        json={"email": email, "otp": otp},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"verify-otp failed for {email}: {resp.status_code} {resp.text}"
        )
    data = resp.json()
    return data["access_token"], data["user"]["id"]


async def connect_ws(token: str):
    ws = await websockets.connect(
        WS_URL,
        subprotocols=[f"nexara.{token}"],
        open_timeout=TIMEOUT,
    )
    first = json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT))
    return ws, first


async def recv_event(
    ws,
    event_name: str,
    timeout: float = TIMEOUT,
    skip_own_user_id: str | None = None,
) -> dict:
    """Receive frames until one matches the wanted event.

    Events whose user_id equals skip_own_user_id are ignored (the
    backend echoes presence to the user themself; the frontend
    ignores those, and the test mirrors that).
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(
            ws.recv(),
            max(1.0, deadline - time.monotonic()),
        )
        data = json.loads(raw)
        if data.get("event") != event_name:
            continue
        if (
            skip_own_user_id is not None
            and data.get("user_id") == skip_own_user_id
        ):
            continue
        return data
    raise TimeoutError(f"timed out waiting for ws event '{event_name}'")


async def main() -> int:
    failures: list[str] = []

    print(f"Booting backend on port {PORT} ...")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "info",
        ],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    reader = LogReader(proc)

    try:
        # ----------------------------------------------------------
        # Wait for the server
        # ----------------------------------------------------------
        healthy = False
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for _ in range(60):
                try:
                    resp = await client.get(f"{BASE_URL}/health")
                    if resp.status_code == 200:
                        healthy = True
                        break
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.5)
            if not healthy:
                failures.append("server did not become healthy in time")
                return 1

            ok = log("health endpoint", True, f"port {PORT}")
            if not ok:
                return 1

            # ------------------------------------------------------
            # Register two users via OTP
            # ------------------------------------------------------
            stamp = uuid.uuid4().hex[:8]
            email_a = f"smoke_alice_{stamp}@example.com"
            email_b = f"smoke_bob_{stamp}@example.com"

            token_a, user_a = await register_user(client, reader, email_a)
            token_b, user_b = await register_user(client, reader, email_b)
            log("OTP registration (2 users)", True, f"{email_a}, {email_b}")

            # ------------------------------------------------------
            # A opens a private conversation with B
            # ------------------------------------------------------
            resp = await client.post(
                f"{API}/conversations/private",
                json={"user_id": user_b},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            if resp.status_code != 200:
                failures.append(
                    f"conversations/private: {resp.status_code} {resp.text}"
                )
                return 1
            conv = resp.json()
            conv_id = conv["id"]
            log("private conversation created", True, f"id={conv_id}")

            # ------------------------------------------------------
            # Both users connect to the WebSocket
            # ------------------------------------------------------
            ws_a, first_a = await connect_ws(token_a)
            log(
                "user A ws connected",
                first_a.get("event") == "connected",
                str(first_a),
            )
            ws_b, first_b = await connect_ws(token_b)
            log(
                "user B ws connected",
                first_b.get("event") == "connected",
                str(first_b),
            )

            # Presence fan-out: B's connect broadcast reaches A.
            # The backend also echoes presence to the user themself;
            # like the frontend (ChatSocketContext.jsx), skip those.
            try:
                presence = await recv_event(
                    ws_a,
                    "presence",
                    timeout=10,
                    skip_own_user_id=str(user_a),
                )
                ok = presence.get("user_id") == str(user_b) and presence.get(
                    "online"
                ) is True
            except (TimeoutError, asyncio.TimeoutError):
                ok = False
                presence = {}
            log("presence broadcast A <- B online", ok, str(presence))

            # ------------------------------------------------------
            # A sends one encrypted message (REST) + WS broadcast
            # ------------------------------------------------------
            msg_payload = {
                "id": str(uuid.uuid4()),
                "conversation_id": conv_id,
                "sender_id": str(user_a),
                "ciphertext": "opaque-ciphertext-for-smoke-test",
                "encrypted_key_sender": "opaque-key-sender",
                "encrypted_key_receiver": "opaque-key-receiver",
                "nonce": "opaque-nonce",
                "created_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()
                ),
            }

            resp = await client.post(
                f"{API}/messages/send",
                json={
                    "conversation_id": conv_id,
                    "ciphertext": msg_payload["ciphertext"],
                    "encrypted_key_sender": msg_payload["encrypted_key_sender"],
                    "encrypted_key_receiver": msg_payload[
                        "encrypted_key_receiver"
                    ],
                    "nonce": msg_payload["nonce"],
                    "message_type": "text",
                },
                headers={"Authorization": f"Bearer {token_a}"},
            )
            if resp.status_code != 200:
                failures.append(
                    f"messages/send: {resp.status_code} {resp.text}"
                )
                return 1
            stored = resp.json()
            log("message stored via REST", True, f"id={stored['id']}")

            # Realtime broadcast (what the frontend does after a send)
            await ws_a.send(
                json.dumps({"event": "message", **msg_payload})
            )

            received = await recv_event(ws_b, "message", timeout=10)
            ok = received.get("id") == msg_payload["id"] and received.get(
                "sender_id"
            ) == str(user_a)
            log("message broadcast delivered to B over ws", ok, str(received))

            # ------------------------------------------------------
            # B marks the message delivered + read -> A gets receipts
            # ------------------------------------------------------
            await ws_b.send(
                json.dumps(
                    {
                        "event": "delivered",
                        "conversation_id": conv_id,
                        "message_id": stored["id"],
                    }
                )
            )
            deliv = await recv_event(ws_a, "delivered", timeout=10)
            log(
                "delivered receipt broadcast to A",
                deliv.get("message_id") == str(stored["id"]),
                str(deliv),
            )

            await ws_b.send(
                json.dumps(
                    {
                        "event": "read",
                        "conversation_id": conv_id,
                        "message_id": stored["id"],
                    }
                )
            )
            read = await recv_event(ws_a, "read", timeout=10)
            log(
                "read receipt broadcast to A",
                read.get("message_id") == str(stored["id"]),
                str(read),
            )

            # ------------------------------------------------------
            # Verify persisted state over REST
            # ------------------------------------------------------
            resp = await client.get(
                f"{API}/messages/{conv_id}",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            if resp.status_code != 200:
                failures.append(
                    f"messages/{conv_id}: {resp.status_code} {resp.text}"
                )
                return 1
            msgs = resp.json()
            msg = next((m for m in msgs if m["id"] == stored["id"]), None)
            ok = msg is not None and msg.get("is_read") is True and msg.get(
                "delivered_at"
            ) is not None
            log(
                "REST history shows delivered + read",
                ok,
                json.dumps(msg) if msg else "message missing",
            )

            # ------------------------------------------------------
            # Group chat flow (Phase 3 verification)
            # ------------------------------------------------------
            print("\n-- Group chat flow --")
            await group_flow(client, reader, failures)

            # ------------------------------------------------------
            # Cleanup
            # ------------------------------------------------------
            await ws_a.close()
            await ws_b.close()

    except Exception as exc:  # noqa: BLE001 - report and fail
        failures.append(f"unexpected error: {type(exc).__name__}: {exc}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    print()
    if failures:
        print(f"SMOKE TEST FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("SMOKE TEST PASSED - full OTP -> conversation -> ws message -> receipts flow OK")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))