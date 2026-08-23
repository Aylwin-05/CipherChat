"""
Generalized conversation-creation tool for Nexara.

Works against ANY running backend (default http://127.0.0.1:8000)
and ANY users in the database. No hardcoded ids or emails.

Examples (run from backend/):

    # One DM
    python scripts/create_conversations.py dm alice@x.com bob@x.com

    # DMs from a hub account to many users
    python scripts/create_conversations.py star hub@x.com a@x.com,b@x.com,c@x.com

    # Every unique pair among the listed users
    python scripts/create_conversations.py pairs a@x.com,b@x.com,c@x.com

    # A group with N members (must already be friends of the creator)
    python scripts/create_conversations.py group owner@x.com "Test Crew" a@x.com,b@x.com

    # Make two users friends (send + accept) so groups are possible
    python scripts/create_conversations.py friend a@x.com b@x.com

    # List a user's conversations
    python scripts/create_conversations.py list alice@x.com

    # Point at another server
    python scripts/create_conversations.py --base-url http://localhost:9000 dm a@x.com b@x.com

Tokens are minted locally from SECRET_KEY (dev convenience), so no
OTP email round-trip is needed.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import httpx
from jose import jwt
from datetime import datetime, timedelta, timezone

from app.core.config import settings


# ==========================================================
# User resolution + token minting (local DB access)
# ==========================================================

def _sync_db_url() -> str:
    url = settings.DATABASE_URL.replace("+asyncpg", "")
    return url


async def resolve_users(client, identifiers):
    """Map emails / uuids / display names -> user rows."""
    conn = await asyncpg.connect(_sync_db_url())
    try:
        resolved = {}
        for identifier in identifiers:
            row = await conn.fetchrow(
                """
                SELECT id, email, display_name FROM users
                WHERE email = $1::text
                   OR id::text = $1
                   OR display_name = $1::text
                LIMIT 1
                """,
                identifier,
            )
            if row is None:
                raise SystemExit(f"User not found: {identifier}")
            resolved[identifier] = dict(row)
        return resolved
    finally:
        await conn.close()


def mint_token(user_row) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    return jwt.encode(
        {
            "sub": str(user_row["id"]),
            "email": user_row["email"],
            "type": "access",
            "exp": expires,
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


# ==========================================================
# API calls
# ==========================================================

class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/") + "/api/v1"
        self.client = httpx.AsyncClient(timeout=30)

    async def close(self):
        await self.client.aclose()

    def _headers(self, user_row):
        return {"Authorization": f"Bearer {mint_token(user_row)}"}

    async def create_private(self, actor, other_id):
        r = await self.client.post(
            f"{self.base}/conversations/private",
            json={"user_id": str(other_id)},
            headers=self._headers(actor),
        )
        _check(r, "create private conversation")
        return r.json()

    async def create_group(self, actor, name, member_ids):
        r = await self.client.post(
            f"{self.base}/conversations/group",
            json={"name": name, "member_ids": [str(m) for m in member_ids]},
            headers=self._headers(actor),
        )
        _check(r, "create group")
        return r.json()

    async def send_friend_request(self, actor, receiver_id):
        r = await self.client.post(
            f"{self.base}/friends/request",
            json={"receiver_id": str(receiver_id)},
            headers=self._headers(actor),
        )
        if r.status_code == 400:
            return None  # probably already friends
        _check(r, "send friend request")
        return r.json()

    async def pending_requests(self, actor):
        r = await self.client.get(
            f"{self.base}/friends/pending",
            headers=self._headers(actor),
        )
        _check(r, "list pending requests")
        return r.json()

    async def accept_request(self, actor, friendship_id):
        r = await self.client.post(
            f"{self.base}/friends/accept",
            json={"friendship_id": str(friendship_id)},
            headers=self._headers(actor),
        )
        _check(r, "accept friend request")
        return r.json()

    async def my_conversations(self, actor):
        r = await self.client.get(
            f"{self.base}/conversations/",
            headers=self._headers(actor),
        )
        _check(r, "list conversations")
        return r.json()


def _check(response, what):
    if response.status_code >= 400:
        detail = response.text[:2000]
        raise SystemExit(
            f"{what} failed: HTTP {response.status_code}\n{detail}"
        )


# ==========================================================
# Commands
# ==========================================================

async def cmd_dm(api, actor_ref, other_ref):
    users = await resolve_users(api.client, [actor_ref, other_ref])
    actor, other = users[actor_ref], users[other_ref]
    conv = await api.create_private(actor, other["id"])
    print(f"DM ready: {conv['id']}  ({actor['display_name']} <-> {other['display_name']})")


async def cmd_star(api, hub_ref, others_csv):
    refs = [hub_ref] + [x.strip() for x in others_csv.split(",") if x.strip()]
    users = await resolve_users(api.client, refs)
    hub = users[hub_ref]
    for ref in refs[1:]:
        conv = await api.create_private(hub, users[ref]["id"])
        print(f"DM ready: {conv['id']}  ({hub['display_name']} <-> {users[ref]['display_name']})")


async def cmd_pairs(api, csv_refs):
    refs = [x.strip() for x in csv_refs.split(",") if x.strip()]
    users = await resolve_users(api.client, refs)
    done = set()
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            key = tuple(sorted((a, b)))
            if key in done:
                continue
            done.add(key)
            conv = await api.create_private(users[a], users[b]["id"])
            print(f"DM ready: {conv['id']}  ({users[a]['display_name']} <-> {users[b]['display_name']})")


async def cmd_group(api, owner_ref, name, members_csv):
    refs = [x.strip() for x in members_csv.split(",") if x.strip()]
    all_refs = [owner_ref] + refs
    users = await resolve_users(api.client, all_refs)
    owner = users[owner_ref]
    members = [users[r]["id"] for r in refs]
    conv = await api.create_group(owner, name, members)
    print(f"Group created: {conv['id']}  \"{name}\" with {len(members) + 1} members")


async def cmd_friend(api, a_ref, b_ref):
    users = await resolve_users(api.client, [a_ref, b_ref])
    a, b = users[a_ref], users[b_ref]
    sent = await api.send_friend_request(a, b["id"])
    if sent is None:
        print(f"Request skipped (already sent or accepted): {a['email']} -> {b['email']}")
        return
    pending = await api.pending_requests(b)
    request_id = next(
        (
            p["id"]
            for p in pending
            if p.get("sender", {}).get("id") == str(a["id"])
            or p.get("sender_id") == str(a["id"])
        ),
        None,
    )
    if request_id is None:
        raise SystemExit("Could not find the pending request to accept.")
    await api.accept_request(b, request_id)
    print(f"Friends: {a['display_name']} <-> {b['display_name']}")


async def cmd_list(api, user_ref):
    (users,) = (await resolve_users(api.client, [user_ref]),)
    user = users[user_ref]
    conversations = await api.my_conversations(user)
    print(f"{len(conversations)} conversation(s) for {user['display_name']} <{user['email']}>:")
    for c in conversations:
        other = c.get("other_user") or {}
        label = c.get("name") or other.get("display_name", "?")
        preview = "message" if c.get("last_message") else "empty"
        print(f"  {c['id']}  [{c.get('conversation_type', 'private')}]  {label}  ({preview})")


COMMANDS = {
    "dm": (cmd_dm, "actor other", 2),
    "star": (cmd_star, "hub others_csv", 2),
    "pairs": (cmd_pairs, "users_csv", 1),
    "group": (cmd_group, "owner name members...", 3),
    "friend": (cmd_friend, "userA userB", 2),
    "list": (cmd_list, "user", 1),
}


async def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("args", nargs="*")
    namespace = parser.parse_args()

    func, usage, min_args = COMMANDS[namespace.command]
    if len(namespace.args) < min_args:
        parser.error(f"'{namespace.command}' expects: {usage}")

    api = Api(namespace.base_url)
    try:
        await func(api, *namespace.args)
    finally:
        await api.close()


if __name__ == "__main__":
    asyncio.run(main())
