// ==========================================================
// Device identity / registration payload tests
// Run: node --test tests/signal/
// ==========================================================

import { test } from "node:test";
import assert from "node:assert/strict";

import {
    generateDeviceIdentity,
    generateOneTimePrekeys,
    generateDeviceId,
    buildRegisterPayload,
    OPK_BATCH_SIZE,
} from "../../src/crypto/signal/identity.js";
import { ed25519Verify } from "../../src/crypto/signal/primitives.js";
import { b64decode } from "../../src/crypto/signal/bytes.js";

test("device identity generation", () => {
    const { identity, signedPrekey } = generateDeviceIdentity({ signedPrekeyId: 7 });
    assert.equal(identity.publicKey.length, 32);
    assert.equal(identity.privateKey.length, 32);
    assert.equal(identity.x25519Public.length, 32);
    assert.equal(signedPrekey.keyId, 7);
    assert.equal(signedPrekey.publicKey.length, 32);
    assert.equal(signedPrekey.signature.length, 64);
});

test("signed prekey signature verifies under identity key", () => {
    const { identity, signedPrekey } = generateDeviceIdentity();
    assert.equal(
        ed25519Verify(
            identity.publicKey,
            signedPrekey.signature,
            signedPrekey.publicKey,
        ),
        true,
    );
});

test("one-time prekeys batch", () => {
    const opks = generateOneTimePrekeys({ startId: 10, count: 5 });
    assert.equal(opks.length, 5);
    assert.deepEqual(opks.map((o) => o.keyId), [10, 11, 12, 13, 14]);
    for (const opk of opks) {
        assert.equal(opk.publicKey.length, 32);
        assert.equal(opk.privateKey.length, 32);
    }
});

test("default batch size is 100", () => {
    assert.equal(OPK_BATCH_SIZE, 100);
    assert.equal(generateOneTimePrekeys().length, 100);
});

test("register payload shape matches backend RegisterDeviceRequest", () => {
    const deviceId = generateDeviceId();
    const { identity, signedPrekey } = generateDeviceIdentity();
    const oneTimePrekeys = generateOneTimePrekeys({ count: 2 });

    const payload = buildRegisterPayload({
        deviceId,
        platform: "web",
        deviceName: "My Browser",
        platformVersion: "Chrome 120",
        appVersion: "1.0.0",
        identity,
        signedPrekey,
        oneTimePrekeys,
    });

    assert.equal(payload.device_id, deviceId);
    assert.equal(payload.platform, "web");
    assert.equal(payload.device_name, "My Browser");
    assert.ok(payload.identity_key_public);
    assert.ok(payload.identity_key_x25519);
    assert.ok(payload.identity_key_private_encrypted);
    assert.ok(payload.signed_prekey_public);
    assert.ok(payload.signed_prekey_private_encrypted);
    assert.equal(payload.signed_prekey_id, 1);
    assert.ok(payload.signed_prekey_signature);
    assert.equal(payload.one_time_prekeys.length, 2);
    for (const opk of payload.one_time_prekeys) {
        assert.equal(typeof opk.key_id, "number");
        assert.ok(opk.public_key);
        assert.ok(opk.private_key_encrypted);
    }

    // public keys re-encode to 32 raw bytes
    assert.equal(b64decode(payload.identity_key_public).length, 32);
    assert.equal(b64decode(payload.identity_key_x25519).length, 32);

    // device id fits backend constraint (8..64 chars)
    assert.ok(deviceId.length >= 8 && deviceId.length <= 64);
});

test("device id generation is unique", () => {
    const ids = new Set(Array.from({ length: 20 }, () => generateDeviceId()));
    assert.equal(ids.size, 20);
});