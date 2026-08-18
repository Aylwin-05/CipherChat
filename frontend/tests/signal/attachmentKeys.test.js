// ==========================================================
// Integration test: per-device attachment file-key wrapping
//
// Mirrors the send flow: the sender wraps the file's AES key
// with encryptBytesForDevices() (the same machinery that wraps
// text messages), the backend stores the envelopes, and any
// receiving device unwraps its own copy with
// decryptEnvelopeBytes().
//
// Also covers the reordering that the 5s "Sent" hold creates:
// the attachment event reaches the peer BEFORE the message
// relay, so the file-key envelope is decrypted first, must
// fail cleanly (no session yet), and must succeed once the
// handshake text envelope arrives.
//
// Run: node --test tests/signal/
// ==========================================================

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";

import { SignalKeyStore } from "../../src/crypto/signal/keyStore.js";
import {
    encryptForConversation,
    encryptBytesForDevices,
    decryptMessage,
    decryptEnvelopeBytes,
} from "../../src/services/signalChatService.js";
import {
    generateDeviceIdentity,
    generateOneTimePrekeys,
} from "../../src/crypto/signal/identity.js";
import { createKeyBundle } from "../../src/crypto/signal/x3dh.js";
import { b64encode } from "../../src/crypto/signal/bytes.js";

let aliceStore;
let bobStore;
let bobBundle;
let aliceBundle;

const CONVERSATION_ID = "conv-file-keys";
const ALICE_DEVICE_ID = "alice-dev-1";
const BOB_DEVICE_ID = "bob-dev-1";

function transport(serializable) {
    return JSON.parse(JSON.stringify(serializable));
}

function randomFileKey() {
    const bytes = new Uint8Array(32);
    for (let i = 0; i < bytes.length; i++) {
        bytes[i] = (i * 7 + 3) % 256;
    }
    return bytes;
}

beforeEach(async () => {
    aliceStore = new SignalKeyStore("test-alice-fk");
    bobStore = new SignalKeyStore("test-bob-fk");

    await aliceStore.clearAll();
    await bobStore.clearAll();

    const alice = generateDeviceIdentity({});
    const aliceOpks = generateOneTimePrekeys({ startId: 1, count: 3 });
    await aliceStore.saveIdentity({
        deviceId: ALICE_DEVICE_ID,
        identityKeyPrivate: b64encode(alice.identity.privateKey),
        identityKeyPublic: b64encode(alice.identity.publicKey),
        x25519IdentityKeyPublic: b64encode(alice.identity.x25519Public),
    });
    await aliceStore.saveMeta({ deviceId: ALICE_DEVICE_ID });
    await aliceStore.saveOneTimePrekeys(
        aliceOpks.map((opk) => ({
            keyId: opk.keyId,
            publicKey: b64encode(opk.publicKey),
            privateKey: b64encode(opk.privateKey),
        })),
    );

    aliceBundle = createKeyBundle({
        deviceId: ALICE_DEVICE_ID,
        identityKeyPrivate: alice.identity.privateKey,
        signedPrekeyPrivate: alice.signedPrekey.privateKey,
        signedPrekeyId: alice.signedPrekey.keyId,
        oneTimePrekeys: aliceOpks,
    });

    const bob = generateDeviceIdentity({});
    const bobOpks = generateOneTimePrekeys({ startId: 1, count: 3 });
    const bobSpk = bob.signedPrekey;

    await bobStore.saveIdentity({
        deviceId: BOB_DEVICE_ID,
        identityKeyPrivate: b64encode(bob.identity.privateKey),
        identityKeyPublic: b64encode(bob.identity.publicKey),
        x25519IdentityKeyPublic: b64encode(bob.identity.x25519Public),
    });
    await bobStore.saveMeta({ deviceId: BOB_DEVICE_ID });
    await bobStore.saveSignedPrekey({
        keyId: bobSpk.keyId,
        publicKey: b64encode(bobSpk.publicKey),
        signature: b64encode(bobSpk.signature),
        privateKey: b64encode(bobSpk.privateKey),
    });
    await bobStore.saveOneTimePrekeys(
        bobOpks.map((opk) => ({
            keyId: opk.keyId,
            publicKey: b64encode(opk.publicKey),
            privateKey: b64encode(opk.privateKey),
        })),
    );

    bobBundle = createKeyBundle({
        deviceId: BOB_DEVICE_ID,
        identityKeyPrivate: bob.identity.privateKey,
        signedPrekeyPrivate: bobSpk.privateKey,
        signedPrekeyId: bobSpk.keyId,
        oneTimePrekeys: bobOpks,
    });
});

test("file key wraps for the recipient device and unwraps there", async () => {
    // Establish the text session first (exactly like the send
    // flow: encryptForDevices runs before the file wraps).
    const text = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "hello + attachment",
        remoteDevices: [bobBundle],
        keyStore: aliceStore,
    });
    await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transport(text.ciphertext),
        keyStore: bobStore,
    });

    const rawKey = randomFileKey();

    const wrapped = await encryptBytesForDevices({
        conversationId: CONVERSATION_ID,
        bytes: rawKey,
        devices: [bobBundle],
        keyStore: aliceStore,
    });

    assert.equal(wrapped.length, 1);
    assert.equal(wrapped[0].device_id, BOB_DEVICE_ID);

    // Data envelope: the established ratchet, sent after the text.
    const envelope = SignalEnvelopeLike(wrapped[0].data);
    assert.equal(envelope.type, "data");

    const unwrapped = await decryptEnvelopeBytes({
        conversationId: CONVERSATION_ID,
        envelopeJson: transport(wrapped[0].data),
        keyStore: bobStore,
    });

    assert.deepEqual(
        new Uint8Array(unwrapped),
        rawKey,
    );
});

test("own device is never wrapped (no (me, me) ratchet)", async () => {
    const rawKey = randomFileKey();

    const wrapped = await encryptBytesForDevices({
        conversationId: CONVERSATION_ID,
        bytes: rawKey,
        devices: [aliceBundle, bobBundle],
        keyStore: aliceStore,
    });

    const deviceIds = wrapped.map((entry) => entry.device_id);
    assert.deepEqual(deviceIds, [BOB_DEVICE_ID]);
});

test("reordered delivery: file envelope first, text handshake second", async () => {
    // Send flow: text envelope (handshake) then file-key
    // envelope, both before the relay. But the attachment
    // event reaches the peer BEFORE the message relay, so the
    // peer decrypts the file key first.
    const text = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "image coming",
        remoteDevices: [bobBundle],
        keyStore: aliceStore,
    });

    const rawKey = randomFileKey();

    const wrapped = await encryptBytesForDevices({
        conversationId: CONVERSATION_ID,
        bytes: rawKey,
        devices: [bobBundle],
        keyStore: aliceStore,
    });

    // 1) File key arrives first: no session yet -> must throw.
    await assert.rejects(
        decryptEnvelopeBytes({
            conversationId: CONVERSATION_ID,
            envelopeJson: transport(wrapped[0].data),
            keyStore: bobStore,
        }),
    );

    // 2) Text handshake lands: builds the session.
    const bobPlain = await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transport(text.ciphertext),
        keyStore: bobStore,
    });
    assert.equal(bobPlain, "image coming");

    // 3) Retry the file key: session now exists -> unwraps.
    const unwrapped = await decryptEnvelopeBytes({
        conversationId: CONVERSATION_ID,
        envelopeJson: transport(wrapped[0].data),
        keyStore: bobStore,
    });

    assert.deepEqual(
        new Uint8Array(unwrapped),
        rawKey,
    );
});

function SignalEnvelopeLike(json) {
    return JSON.parse(json);
}