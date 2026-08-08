// ==========================================================
// Key store tests (Node with fake-indexeddb)
// Run: node --test tests/signal/
// ==========================================================

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";

import { SignalKeyStore } from "../../src/crypto/signal/keyStore.js";

let store;

beforeEach(() => {
    store = new SignalKeyStore();
});

test("identity roundtrip", async () => {
    await store.saveIdentity({
        deviceId: "web-abc",
        identityKeyPrivate: "priv",
        identityKeyPublic: "pub",
        x25519IdentityKeyPublic: "xpub",
    });
    const identity = await store.getIdentity();
    assert.equal(identity.deviceId, "web-abc");
    assert.equal(identity.identityKeyPublic, "pub");
    assert.equal(identity.x25519IdentityKeyPublic, "xpub");
});

test("signed prekey roundtrip and clear", async () => {
    await store.saveSignedPrekey({
        keyId: 1,
        publicKey: "spk-pub",
        signature: "sig",
        privateKey: "spk-priv",
    });
    const spk = await store.getSignedPrekey(1);
    assert.equal(spk.privateKey, "spk-priv");

    await store.saveSignedPrekey({
        keyId: 2,
        publicKey: "spk-pub-2",
        signature: "sig2",
        privateKey: "spk-priv-2",
    });
    const all = await store.getAllSignedPrekeys();
    assert.equal(all.length, 2);
    assert.equal(all[1].keyId, 2);

    await store.clearSignedPrekeys();
    assert.equal((await store.getAllSignedPrekeys()).length, 0);
});

test("one-time prekeys roundtrip, count and removal", async () => {
    await store.saveOneTimePrekeys([
        { keyId: 1, publicKey: "p1", privateKey: "k1" },
        { keyId: 2, publicKey: "p2", privateKey: "k2" },
    ]);
    assert.equal(await store.getOneTimePrekeyCount(), 2);

    await store.removeOneTimePrekey(1);
    assert.equal(await store.getOneTimePrekeyCount(), 1);
    const remaining = await store.getAllOneTimePrekeys();
    assert.equal(remaining[0].keyId, 2);

    await store.clearOneTimePrekeys();
    assert.equal(await store.getOneTimePrekeyCount(), 0);
});

test("sessions roundtrip and delete", async () => {
    const key = {
        ourDeviceId: "web-a",
        remoteDeviceId: "web-b",
        conversationId: "conv-1",
    };
    const state = { root_key: "hex", sending_chain: { key: "x", index: 2 } };

    assert.equal(await store.getSession(key), null);
    await store.saveSession(key, state);
    assert.deepEqual(await store.getSession(key), state);

    const other = { ...key, remoteDeviceId: "web-c" };
    assert.equal(await store.getSession(other), null);

    await store.deleteSession(key);
    assert.equal(await store.getSession(key), null);
});

test("meta roundtrip and clearAll wipes everything", async () => {
    await store.saveMeta({ deviceId: "web-xyz", isPrimary: true });
    const meta = await store.getMeta();
    assert.equal(meta.deviceId, "web-xyz");
    assert.equal(meta.isPrimary, true);

    await store.saveIdentity({
        deviceId: "web-xyz",
        identityKeyPrivate: "p",
        identityKeyPublic: "q",
        x25519IdentityKeyPublic: "r",
    });
    await store.saveOneTimePrekeys([{ keyId: 9, publicKey: "x", privateKey: "y" }]);
    await store.saveSession(
        { ourDeviceId: "a", remoteDeviceId: "b", conversationId: "c" },
        { root_key: "1" },
    );

    await store.clearAll();
    assert.equal(await store.getMeta(), null);
    assert.equal(await store.getIdentity(), null);
    assert.equal(await store.getOneTimePrekeyCount(), 0);
    assert.equal(
        await store.getSession({ ourDeviceId: "a", remoteDeviceId: "b", conversationId: "c" }),
        null,
    );
});