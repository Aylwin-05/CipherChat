// ==========================================================
// JS mirror of backend/tests/test_signal_protocol.py
// Run: node --test tests/signal/
// ==========================================================

import { test } from "node:test";
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";

import {
    generateX25519Keypair,
    generateEd25519Keypair,
    x25519Dh,
    ed25519Sign,
    ed25519Verify,
    kdfRootChain,
    kdfChainKey,
    aesGcmEncrypt,
    aesGcmDecrypt,
    generateSymmetricKey,
    generateNonce,
    deriveMessageKeys,
} from "../../src/crypto/signal/primitives.js";
import {
    DoubleRatchetCore,
    RatchetState,
    DHKeyPair,
    Chain,
} from "../../src/crypto/signal/doubleRatchet.js";
import {
    SignalEnvelope,
    EnvelopeError,
    buildPrekeyMessage,
    parsePrekeyMessage,
} from "../../src/crypto/signal/message.js";

const utf8 = (s) => new TextEncoder().encode(s);

// ==========================================================
// Primitives
// ==========================================================

test("x25519 DH matches both sides", () => {
    const a = generateX25519Keypair();
    const b = generateX25519Keypair();
    assert.deepEqual(x25519Dh(a.privateKey, b.publicKey), x25519Dh(b.privateKey, a.publicKey));
});

test("ed25519 sign/verify", () => {
    const { privateKey, publicKey } = generateEd25519Keypair();
    const sig = ed25519Sign(privateKey, utf8("hello"));
    assert.equal(ed25519Verify(publicKey, sig, utf8("hello")), true);
    assert.equal(ed25519Verify(publicKey, sig, utf8("tampered")), false);
});

test("kdf root chain lengths", () => {
    const root = new Uint8Array(32).fill(0x52); // b"R"*32
    const dh = new Uint8Array(32).fill(0x44);   // b"D"*32
    const { rootKey, chainKey } = kdfRootChain(root, dh);
    assert.equal(rootKey.length, 32);
    assert.equal(chainKey.length, 32);
});

test("kdf chain key distinct outputs", () => {
    const ck = new Uint8Array(32).fill(0x43);
    const { nextChainKey, messageKey } = kdfChainKey(ck);
    assert.equal(nextChainKey.length, 32);
    assert.equal(messageKey.length, 32);
    assert.notDeepEqual(nextChainKey, messageKey);
});

test("aes-gcm roundtrip", () => {
    const key = generateSymmetricKey();
    const nonce = generateNonce();
    const ad = utf8("AD");
    const { ciphertext, nonce: used } = aesGcmEncrypt(key, utf8("secret"), ad, nonce);
    assert.deepEqual(aesGcmDecrypt(key, ciphertext, ad, used), utf8("secret"));
});

test("aes-gcm tamper fails", () => {
    const key = generateSymmetricKey();
    const nonce = generateNonce();
    const { ciphertext, nonce: used } = aesGcmEncrypt(key, utf8("secret"), utf8("AD"), nonce);
    const tampered = slice(ciphertext);
    tampered[tampered.length - 1] ^= 1;
    assert.throws(() => aesGcmDecrypt(key, tampered, utf8("AD"), used));
});

// ==========================================================
// Double Ratchet
// ==========================================================

test("message key derivation deterministic", () => {
    const mk = new TextEncoder().encode("MKMKMKMKMKMKMKMK"); // b"MK"*16
    const e1 = deriveMessageKeys(mk);
    const e2 = deriveMessageKeys(mk);
    assert.deepEqual(e1.encKey, e2.encKey);
    assert.deepEqual(e1.authKey, e2.authKey);
    assert.equal(e1.encKey.length, 32);
    assert.equal(e1.authKey.length, 32);
});

test("ratchet state roundtrip", () => {
    const state = new RatchetState({
        rootKey: new Uint8Array(32).fill(0x52),
        ourDhPair: DHKeyPair.new(),
        theirDhPublic: new Uint8Array(32).fill(0x54),
        sendingChain: new Chain(new Uint8Array(32).fill(0x53), 5),
        receivingChain: new Chain(new Uint8Array(32).fill(0x43), 3),
        skippedMessageKeys: {},
        associatedData: new Uint8Array(64).fill(0x41),
    });
    const state2 = RatchetState.fromDict(JSON.parse(JSON.stringify(state.toDict())));
    assert.deepEqual(state2.rootKey, state.rootKey);
    assert.deepEqual(state2.ourDhPair.publicRaw, state.ourDhPair.publicRaw);
    assert.equal(state2.sendingChain.index, 5);
});

test("bidirectional ratchet", () => {
    const shared = new Uint8Array(32).fill(0x53);
    const ad = new Uint8Array(64).fill(0x41);
    const alice = new DoubleRatchetCore(shared, ad);
    const bob = new DoubleRatchetCore(shared, ad);

    alice.theirDhPublic = bob.ourDhPair.publicRaw;
    alice.initializeInitiator();

    let { header, payload } = alice.encrypt_message(utf8("Hello"));
    assert.deepEqual(bob.decrypt_message(header, payload), utf8("Hello"));

    let r = bob.encrypt_message(utf8("Hi"));
    assert.deepEqual(alice.decrypt_message(r.header, r.payload), utf8("Hi"));

    for (let i = 0; i < 20; i++) {
        const a = alice.encrypt_message(utf8(`A${i}`));
        assert.deepEqual(bob.decrypt_message(a.header, a.payload), utf8(`A${i}`));
        const b = bob.encrypt_message(utf8(`B${i}`));
        assert.deepEqual(alice.decrypt_message(b.header, b.payload), utf8(`B${i}`));
    }
});

test("out-of-order delivery", () => {
    const shared = new Uint8Array(32).fill(0x53);
    const ad = new Uint8Array(64).fill(0x41);
    const alice = new DoubleRatchetCore(shared, ad);
    const bob = new DoubleRatchetCore(shared, ad);
    alice.theirDhPublic = bob.ourDhPair.publicRaw;
    alice.initializeInitiator();

    const msgs = [];
    for (let i = 0; i < 5; i++) {
        msgs.push(alice.encrypt_message(utf8(`M${i}`)));
    }
    for (const i of [2, 0, 1, 4, 3]) {
        assert.deepEqual(bob.decrypt_message(msgs[i].header, msgs[i].payload), utf8(`M${i}`));
    }
    // replay rejected
    assert.throws(() => bob.decrypt_message(msgs[0].header, msgs[0].payload));
});

test("state save/restore", () => {
    const ad = new Uint8Array(64).fill(0x41);
    const alice = new DoubleRatchetCore(new Uint8Array(32).fill(0x53), ad);
    const bob = new DoubleRatchetCore(new Uint8Array(32).fill(0x53), ad);
    alice.theirDhPublic = bob.ourDhPair.publicRaw;
    alice.initializeInitiator();

    for (let i = 0; i < 3; i++) {
        const m = alice.encrypt_message(utf8(`M${i}`));
        bob.decrypt_message(m.header, m.payload);
    }

    const restored = DoubleRatchetCore.fromState(
        RatchetState.fromDict(JSON.parse(JSON.stringify(alice.state().toDict()))),
    );
    const m = restored.encrypt_message(utf8("M3"));
    assert.deepEqual(bob.decrypt_message(m.header, m.payload), utf8("M3"));
});

// ==========================================================
// Envelope
// ==========================================================

test("prekey envelope roundtrip", () => {
    const ek = generateX25519Keypair();
    const ik = generateEd25519Keypair();
    const env = buildPrekeyMessage({
        deviceId: "d1",
        senderId: "u1",
        ourIdentityPrivate: ik.privateKey,
        ourEphemeralPrivate: ek.privateKey,
        ratchetHeader: { pn: 0, n: 0, dh: "ab".repeat(32) },
        ciphertext: new Uint8Array([1, 2]),
        signedPrekeyId: 1,
        oneTimePrekeyId: 3,
    });
    const env2 = SignalEnvelope.fromJson(env.toJson());
    const info = parsePrekeyMessage(env2);
    assert.equal(info.signedPrekeyId, 1);
    assert.equal(info.oneTimePrekeyId, 3);
});

test("malformed envelope rejected", () => {
    assert.throws(() => SignalEnvelope.fromJson("not json"), EnvelopeError);
    assert.throws(
        () =>
            SignalEnvelope.fromJson(
                JSON.stringify({
                    type: "data",
                    version: 99,
                    device_id: "d",
                    sender_id: "s",
                    ratchet: {},
                    ciphertext: "",
                }),
            ),
        EnvelopeError,
    );
});

// ==========================================================
// Helpers
// ==========================================================

function slice(bytes) {
    return Uint8Array.from(bytes);
}