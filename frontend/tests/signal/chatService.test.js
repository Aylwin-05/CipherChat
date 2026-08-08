// ==========================================================
// Integration test: signalChatService end-to-end
//
// Simulates two users on two separate devices (separate
// IndexedDB stores via fake-indexeddb):
//
//   Alice (device "alice-dev-1")  <->  Bob (device "bob-dev-1")
//
// Exercises the exact service entrypoints the chat UI uses:
//   encryptForConversation()  ->  decryptMessage()
// across the X3DH handshake AND the established double-ratchet
// session, with the ciphertext JSON surviving a "transport"
// round trip (JSON.parse/stringify like the backend would).
//
// Run: node --test tests/signal/
// ==========================================================

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";

import { SignalKeyStore } from "../../src/crypto/signal/keyStore.js";
import {
    encryptForConversation,
    decryptMessage,
} from "../../src/services/signalChatService.js";
import {
    generateDeviceIdentity,
    generateOneTimePrekeys,
} from "../../src/crypto/signal/identity.js";
import { createKeyBundle } from "../../src/crypto/signal/x3dh.js";
import { b64encode } from "../../src/crypto/signal/bytes.js";

// ----------------------------------------------------------
// Fixtures: one store + registered device per user
// ----------------------------------------------------------

let aliceStore;
let bobStore;
let bobBundle; // published to the server, fetched by Alice
let aliceBundle; // published to the server, fetched by Bob

const CONVERSATION_ID = "conv-42";
const ALICE_DEVICE_ID = "alice-dev-1";
const BOB_DEVICE_ID = "bob-dev-1";

function transport(serializable) {
    return JSON.parse(JSON.stringify(serializable));
}

beforeEach(async () => {
    aliceStore = new SignalKeyStore("test-alice");
    bobStore = new SignalKeyStore("test-bob");

    // fake-indexeddb databases persist across tests in one
    // process; wipe so each test starts from a clean slate.
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

    // The bundle Bob would fetch from GET /devices/{id}/bundle
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

    // The bundle Alice would fetch from GET /devices/{id}/bundle
    bobBundle = createKeyBundle({
        deviceId: BOB_DEVICE_ID,
        identityKeyPrivate: bob.identity.privateKey,
        signedPrekeyPrivate: bobSpk.privateKey,
        signedPrekeyId: bobSpk.keyId,
        oneTimePrekeys: bobOpks,
    });
});

test("full round trip: X3DH handshake then ratcheted messages", async () => {
    // ---- Alice sends the first message (handshake) ----
    const first = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "Hello Bob, this is Alice!",
        remoteDevices: [bobBundle],
        keyStore: aliceStore,
    });
    assert.equal(first.type, "prekey");

    // Transport: the ciphertext the backend would store/forward
    const transported = {
        ciphertext: transport(first.ciphertext),
    };

    const bobPlain = await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transported.ciphertext,
        keyStore: bobStore,
    });
    assert.equal(bobPlain, "Hello Bob, this is Alice!");

    // Bob's one-time prekey is single use
    assert.equal(await bobStore.getOneTimePrekeyCount(), 2);

    // ---- Bob replies (established session) ----
    const bobReply = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        otherUserId: "user-alice",
        plaintext: "Got it, Alice!",
        remoteDevices: [aliceBundle],
        keyStore: bobStore,
    });
    assert.equal(bobReply.type, "data");

    const alice = await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transport(bobReply.ciphertext),
        keyStore: aliceStore,
    });
    assert.equal(alice, "Got it, Alice!");

    // ---- 5 messages each way over the ratchet ----
    for (let i = 0; i < 5; i++) {
        const a = await encryptForConversation({
            conversationId: CONVERSATION_ID,
            plaintext: `A${i}`,
            keyStore: aliceStore,
        });
        const ra = await decryptMessage({
            conversationId: CONVERSATION_ID,
            ciphertext: transport(a.ciphertext),
            keyStore: bobStore,
        });
        assert.equal(ra, `A${i}`);

        const b = await encryptForConversation({
            conversationId: CONVERSATION_ID,
            plaintext: `B${i}`,
            keyStore: bobStore,
        });
        const rb = await decryptMessage({
            conversationId: CONVERSATION_ID,
            ciphertext: transport(b.ciphertext),
            keyStore: aliceStore,
        });
        assert.equal(rb, `B${i}`);
    }
});

test("peer device identity is pinned after first handshake", async () => {
    // First handshake pins bob-dev-1 for the conversation.
    // Subsequent sends MUST NOT re-run X3DH (no OPK consumed).
    const first = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "pin me",
        remoteDevices: [bobBundle],
        keyStore: aliceStore,
    });
    await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transport(first.ciphertext),
        keyStore: bobStore,
    });

    // OPK consumed by Bob during the handshake
    assert.equal(await bobStore.getOneTimePrekeyCount(), 2);

    // Second send: established session, no new OPK touched
    const second = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "second",
        keyStore: aliceStore,
    });
    assert.equal(second.type, "data");
    const got = await decryptMessage({
        conversationId: CONVERSATION_ID,
        ciphertext: transport(second.ciphertext),
        keyStore: bobStore,
    });
    assert.equal(got, "second");

    // Still only the one OPK from the original handshake
    assert.equal(await bobStore.getOneTimePrekeyCount(), 2);
});

test("attacker with no session cannot decrypt", async () => {
    const attackerStore = new SignalKeyStore("test-eve");
    const eve = generateDeviceIdentity({});
    await attackerStore.saveIdentity({
        deviceId: "eve-dev-1",
        identityKeyPrivate: b64encode(eve.identity.privateKey),
        identityKeyPublic: b64encode(eve.identity.publicKey),
        x25519IdentityKeyPublic: b64encode(eve.identity.x25519Public),
    });
    await attackerStore.saveMeta({ deviceId: "eve-dev-1" });

    const aliceEnv = await encryptForConversation({
        conversationId: CONVERSATION_ID,
        plaintext: "classified",
        remoteDevices: [bobBundle],
        keyStore: aliceStore,
    });

    await assert.rejects(
        decryptMessage({
            conversationId: CONVERSATION_ID,
            ciphertext: transport(aliceEnv.ciphertext),
            keyStore: attackerStore,
        }),
    );
});

test("non-Signal ciphertext rejects via decryptMessage", async () => {
    await assert.rejects(
        decryptMessage({
            conversationId: CONVERSATION_ID,
            ciphertext: "not-an-envelope",
            keyStore: aliceStore,
        }),
    );
});