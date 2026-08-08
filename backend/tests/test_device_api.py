"""API integration tests for the devices / key-bundle endpoints."""

import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.api.v1.api import api_router
from app.crypto.signal.primitives import (
    b64encode,
    ed25519_private_to_bytes,
    ed25519_public_to_bytes,
    ed25519_sign,
    generate_ed25519_keypair,
    generate_x25519_keypair,
    x25519_private_to_bytes,
    x25519_public_to_bytes,
)
from app.crypto.signal.x3dh import derive_x25519_from_ed25519
from app.database.base import Base
from app.database.session import get_db
from app.dependencies.auth import get_current_user
from app.main import app as app_instance
from app.models.user import User
import app.services.encryption_service as encryption_service_module


def _fernet_key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def client(monkeypatch):
    # Point the server Fernet master key at a test key
    monkeypatch.setattr(
        encryption_service_module.settings, "MASTER_KEY", _fernet_key()
    )

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    async def override_get_current_user():
        async with TestingSessionLocal() as session:
            return await session.get(User, _USER_ID)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestingSessionLocal() as session:
            session.add(User(
                id=_USER_ID,
                email="alice@example.com",
                username="alice",
                display_name="Alice",
            ))
            await session.commit()

    import asyncio
    asyncio.run(setup())

    app_instance.dependency_overrides[get_db] = override_get_db
    app_instance.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app_instance) as test_client:
        yield test_client

    app_instance.dependency_overrides.clear()


_USER_ID = uuid.UUID("abcdef12-3456-7890-abcd-ef1234567890")


def make_key_material(client_store_password: bytes = b"pass", opk_count: int = 3) -> dict:
    """Simulate client-side generation of Signal identity/prekeys."""

    identity_priv, identity_pub = generate_ed25519_keypair()
    identity_x25519 = derive_x25519_from_ed25519(identity_priv)
    identity_x25519_pub = identity_x25519.public_key()

    spk_priv, spk_pub = generate_x25519_keypair()
    spk_pub_bytes = x25519_public_to_bytes(spk_pub)
    signature = ed25519_sign(identity_priv, spk_pub_bytes)

    opks = []
    for kid in range(1, opk_count + 1):
        p, q = generate_x25519_keypair()
        opks.append({
            "key_id": kid,
            "public_key": b64encode(x25519_public_to_bytes(q)),
            "private_key_encrypted": b64encode(
                b64encode(x25519_private_to_bytes(p)).encode()
            ),
        })

    return {
        "identity_key_public": b64encode(ed25519_public_to_bytes(identity_pub)),
        "identity_key_x25519": b64encode(x25519_public_to_bytes(identity_x25519_pub)),
        "identity_key_private_encrypted": b64encode(
            b64encode(ed25519_private_to_bytes(identity_priv)).encode()
        ),
        "signed_prekey_public": b64encode(spk_pub_bytes),
        "signed_prekey_private_encrypted": b64encode(
            b64encode(x25519_private_to_bytes(spk_priv)).encode()
        ),
        "signed_prekey_id": 1,
        "signed_prekey_signature": b64encode(signature),
        "one_time_prekeys": opks,
    }

# ==========================================================
# Register Device
# ==========================================================

def test_register_device_primary(client):
    resp = client.post(
        "/api/v1/devices/register",
        json={
            "device_id": str(uuid.uuid4()),
            "platform": "web",
            "device_name": "Alice's Laptop",
            **make_key_material(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["is_primary"] is True


def test_register_second_device_not_primary(client):
    km = make_key_material()
    resp = client.post(
        "/api/v1/devices/register",
        json={
            "device_id": str(uuid.uuid4()),
            "platform": "web",
            "device_name": "Primary",
            **km,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_primary"] is True

    resp2 = client.post(
        "/api/v1/devices/register",
        json={
            "device_id": str(uuid.uuid4()),
            "platform": "ios",
            "device_name": "iPhone",
            **make_key_material(),
        },
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["is_primary"] is False


# ==========================================================
# Key Bundle
# ==========================================================

def test_get_key_bundle(client):
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": str(uuid.uuid4()),
            **make_key_material(),
        },
    )

    resp = client.get(f"/api/v1/devices/{_USER_ID}/bundle")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == str(_USER_ID)
    assert len(body["devices"]) == 1

    device = body["devices"][0]
    assert device["identity_key"]
    assert device["x25519_identity_key"]
    assert device["signed_prekey"]["signature"]
    assert len(device["one_time_prekeys"]) == 1  # only 1 served


def test_get_bundle_unknown_user_404(client):
    resp = client.get(
        f"/api/v1/devices/{uuid.uuid4()}/bundle"
    )
    assert resp.status_code == 404


# ==========================================================
# Replenish PreKeys
# ==========================================================

def test_replenish_prekeys(client):
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": str(uuid.uuid4()),
            **make_key_material(opk_count=0),
        },
    )

    resp = client.post("/api/v1/devices/prekeys/replenish")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert len(body["one_time_prekeys"]) == 100


# ==========================================================
# Upload Client-Generated PreKeys
# ==========================================================

def test_upload_prekeys(client):
    device_id = str(uuid.uuid4())
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": device_id,
            **make_key_material(opk_count=0),
        },
    )

    batch = make_key_material(opk_count=5)["one_time_prekeys"]
    resp = client.post(
        "/api/v1/devices/prekeys/upload",
        json={"device_id": device_id, "one_time_prekeys": batch},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["one_time_prekeys"]) == 5

    # Serve exactly one new prekey per bundle request
    bundle = client.get(f"/api/v1/devices/{_USER_ID}/bundle").json()
    served = bundle["devices"][0]["one_time_prekeys"]
    assert len(used := [k for k in batch if k["key_id"] == served[0]["key_id"]]) == 1

    # Idempotent: re-uploading the same batch stores nothing new
    resp2 = client.post(
        "/api/v1/devices/prekeys/upload",
        json={"device_id": device_id, "one_time_prekeys": batch},
    )
    assert resp2.status_code == 200, resp2.text
    assert len(resp2.json()["one_time_prekeys"]) == 0


def test_upload_prekeys_unknown_device_404(client):
    resp = client.post(
        "/api/v1/devices/prekeys/upload",
        json={
            "device_id": "no-such-device",
            "one_time_prekeys": make_key_material(opk_count=2)["one_time_prekeys"],
        },
    )
    assert resp.status_code == 404


# ==========================================================
# List Devices
# ==========================================================

def test_list_devices(client):
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": "dev-0001",
            "device_name": "Primary",
            **make_key_material(),
        },
    )
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": "dev-0002",
            "device_name": "Secondary",
            **make_key_material(),
        },
    )

    resp = client.get("/api/v1/devices/me")
    assert resp.status_code == 200, resp.text
    devices = resp.json()["devices"]
    assert len(devices) == 2
    assert any(d["is_primary"] for d in devices)


# ==========================================================
# Remove Device
# ==========================================================

def test_remove_secondary_device(client):
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": "dev-0001",
            **make_key_material(),
        },
    )
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": "dev-0002",
            **make_key_material(),
        },
    )

    resp = client.delete("/api/v1/devices/dev-0002")
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True

    remaining = client.get("/api/v1/devices/me").json()["devices"]
    assert len(remaining) == 1


def test_cannot_remove_primary(client):
    client.post(
        "/api/v1/devices/register",
        json={
            "device_id": "dev-0001",
            **make_key_material(),
        },
    )

    resp = client.delete("/api/v1/devices/dev-0001")
    assert resp.status_code == 400
