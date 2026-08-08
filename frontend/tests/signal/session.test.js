// ==========================================================
// JS mirror of backend/tests/test_signal_session.py
// Run: node --test tests/signal/
// ==========================================================

import { test } from "node:test";
import assert from "node:assert/strict";

import {
    SignalSessionManager,
    InMemorySessionStore,
} from "../../src/crypto/signal/session.js";
import {
    generateEd25519Keypair,
    generateX25519Keypair,
} from "../../src/crypto/signal/primitives.js";
import { createKeyBundle } from "../../src/crypto/signal/x3dh.js";
import { b64encode } from "../../src/crypto/signal/bytes.js";
import { RatchetState } from "../../src/crypto/signal/doubleRatchet.js";

const utf8 = (s) => new TextEncoder().encode(s);

function makeBundle(bobIk, bobSpk, bobOpk, deviceId = "bob-device-1") {
    return createKeyBundle({
        deviceId,
        identityKeyPrivate: bobIk,
        signedPrekeyPrivate: bobSpk,
        signedPrekeyId: 1,
        oneTimePrekeys: [{ keyId: 7, privateKey: bobOpk }],
    });
}

test("full session flow (X3DH handshake + double ratchet)", async () => {
    // --- Bob's keys + bundle ---
    const bob = generateEd25519Keypair();
    const bobSpk = generateX25519Keypair();
    const bobOpk = generateX25519Keypair();
    const bundle = makeBundle(bob.privateKey, bobSpk.privateKey, bobOpk.privateKey);

    const alice = generateEd25519Keypair();

    const aliceMgr = new SignalSessionManager(new InMemorySessionStore());
    const bobMgr = new SignalSessionManager(new InMemorySessionStore());

    // --- Alice first message (X3DH) ---
    const env1 = await aliceMgr.encryptFirst({
        ourDeviceId: "alice-device-1",
        ourUserId: "user-alice",
        ourIdentityPrivate: alice.privateKey,
        theirDeviceId: "bob-device-1",
        theirBundle: bundle,
        conversationId: "conv-1",
        plaintext: utf8("Hello Bob, this is Alice!"),
    });
    assert.equal(env1.type, "prekey");

    const res1 = await bobMgr.decryptFirst({
        envelope: env1,
        ourDeviceId: "bob-device-1",
        ourIdentityKey: bob.privateKey,
        signedPrekey: {
            key_id: 1,
            private_key: b64encode(bobSpk.privateKey),
        },
        oneTimePrekey: {
            key_id: 7,
            private_key: b64encode(bobOpk.privateKey),
        },
        conversationId: "conv-1",
    });
    assert.deepEqual(res1.plaintext, utf8("Hello Bob, this is Alice!"));
    assert.equal(res1.newSession, true);

    // --- Bob replies ---
    const env2 = await bobMgr.encrypt({
        ourDeviceId: "bob-device-1",
        ourUserId: "user-bob",
        remoteDeviceId: "alice-device-1",
        conversationId: "conv-1",
        plaintext: utf8("Hello Alice, message received!"),
    });
    const res2 = await aliceMgr.decrypt({
        envelope: env2,
        ourDeviceId: "alice-device-1",
        conversationId: "conv-1",
    });
    assert.deepEqual(res2.plaintext, utf8("Hello Alice, message received!"));

    // --- 10 more messages each way ---
    for (let i = 0; i < 10; i++) {
        const env = await aliceMgr.encrypt({
            ourDeviceId: "alice-device-1",
            ourUserId: "user-alice",
            remoteDeviceId: "bob-device-1",
            conversationId: "conv-1",
            plaintext: utf8(`A${i}`),
        });
        const ra = await bobMgr.decrypt({
            envelope: env,
            ourDeviceId: "bob-device-1",
            conversationId: "conv-1",
        });
        assert.deepEqual(ra.plaintext, utf8(`A${i}`));

        const env2 = await bobMgr.encrypt({
            ourDeviceId: "bob-device-1",
            ourUserId: "user-bob",
            remoteDeviceId: "alice-device-1",
            conversationId: "conv-1",
            plaintext: utf8(`B${i}`),
        });
        const rb = await aliceMgr.decrypt({
            envelope: env2,
            ourDeviceId: "alice-device-1",
            conversationId: "conv-1",
        });
        assert.deepEqual(rb.plaintext, utf8(`B${i}`));
    }
});

test("session state persistence", async () => {
    const bob = generateEd25519Keypair();
    const bobSpk = generateX25519Keypair();
    const bobOpk = generateX25519Keypair();
    const bundle = makeBundle(bob.privateKey, bobSpk.privateKey, bobOpk.privateKey);
    const alice = generateEd25519Keypair();

    const aliceStore = new InMemorySessionStore();
    const bobStore = new InMemorySessionStore();
    const aliceMgr = new SignalSessionManager(aliceStore);
    const bobMgr = new SignalSessionManager(bobStore);

    const env1 = await aliceMgr.encryptFirst({
        ourDeviceId: "a-1",
        ourUserId: "u-a",
        ourIdentityPrivate: alice.privateKey,
        theirDeviceId: "b-1",
        theirBundle: bundle,
        conversationId: "c-1",
        plaintext: utf8("first"),
    });
    await bobMgr.decryptFirst({
        envelope: env1,
        ourDeviceId: "b-1",
        ourIdentityKey: bob.privateKey,
        signedPrekey: { key_id: 1, private_key: b64encode(bobSpk.privateKey) },
        oneTimePrekey: { key_id: 7, private_key: b64encode(bobOpk.privateKey) },
        conversationId: "c-1",
    });

    // Restore from serialized state
    const saved = await aliceStore.get("a-1", "b-1", "c-1");
    const restored = RatchetState.fromDict(
        JSON.parse(JSON.stringify(saved.toDict())),
    );
    assert.deepEqual(restored.rootKey, saved.rootKey);

    // Messages still work after restore
    const env = await aliceMgr.encrypt({
        ourDeviceId: "a-1",
        ourUserId: "u-a",
        remoteDeviceId: "b-1",
        conversationId: "c-1",
        plaintext: utf8("after restart"),
    });
    const res = await bobMgr.decrypt({
        envelope: env,
        ourDeviceId: "b-1",
        conversationId: "c-1",
    });
    assert.deepEqual(res.plaintext, utf8("after restart"));
});

test("no session raises", async () => {
    const mgr = new SignalSessionManager(new InMemorySessionStore());
    await assert.rejects(
        mgr.encrypt({
            ourDeviceId: "a",
            ourUserId: "u1",
            remoteDeviceId: "b-1",
            conversationId: "c-1",
            plaintext: utf8("hi"),
        }),
    );
});