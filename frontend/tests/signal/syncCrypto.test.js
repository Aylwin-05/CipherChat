import { test } from "node:test";
import assert from "node:assert/strict";

import "fake-indexeddb/auto";
import { gcm } from "@noble/ciphers/aes.js";

import {
    normalizeRecoveryCode,
    deriveWrapKeyFromCode,
    unwrapSyncSecret,
    encryptSyncText,
    decryptSyncText,
    encryptSyncBytes,
    decryptSyncBytes,
    clearSyncKeyCache,
    SYNC_KEY_SIZE,
} from "../../src/crypto/syncCrypto.js";
import { signalKeyStore } from "../../src/crypto/signal/keyStore.js";

// ==========================================================
// Account sync crypto: recovery code wrap + sync copies
// ==========================================================

test("normalizeRecoveryCode strips formatting and uppercases", () => {
    assert.equal(
        normalizeRecoveryCode("abcd12-efgh34-ijkl56-mnop78"),
        "ABCD12EFGH34IJKL56MNOP78",
    );
});

test("deriveWrapKeyFromCode is deterministic per code+salt", () => {
    const salt = btoa("0123456789abcdef");
    const a = deriveWrapKeyFromCode("ABCDEF", salt);
    const b = deriveWrapKeyFromCode("ABCDEF", salt);
    const c = deriveWrapKeyFromCode("ABCDEG", salt);
    const d = deriveWrapKeyFromCode("ABCDEF", btoa("0123456789abcdeg"));
    assert.deepEqual(a, b);
    assert.equal(a.length, SYNC_KEY_SIZE);
    assert.notDeepEqual(a, c, "different code -> different key");
    assert.notDeepEqual(a, d, "different salt -> different key");
});

test("unwrapSyncSecret roundtrip with a valid code", () => {
    const salt = btoa("0123456789abcdef");
    const wrapped = (() => {
        // Simulate the server wrap: PBKDF2 key + AES-GCM(secret).
        // Built with the same module so the roundtrip is honest.
        const key = deriveWrapKeyFromCode("SECRETCODE1", salt);
        const nonce = new Uint8Array(12).fill(7);
        const secret = new Uint8Array(32).fill(9);
        const data = gcm(key, nonce).encrypt(secret);
        return { nonce: btoa(String.fromCharCode(...nonce)), data: btoa(String.fromCharCode(...data)) };
    })();

    const secret = unwrapSyncSecret("SECRETCODE1", salt, wrapped);
    assert.ok(secret, "valid code unlocks the secret");
    assert.equal(secret.length, 44, "32 bytes -> base64 length 44");
});

test("unwrapSyncSecret rejects a wrong code", () => {
    const salt = btoa("0123456789abcdef");
    const key = deriveWrapKeyFromCode("GOODCODE123", salt);
    const nonce = new Uint8Array(12);
    const data = gcm(key, nonce).encrypt(new Uint8Array(32).fill(1));
    const wrapped = { nonce: btoa(String.fromCharCode(...nonce)), data: btoa(String.fromCharCode(...data)) };

    assert.equal(
        unwrapSyncSecret("WRONGCODE!!", salt, wrapped),
        null,
        "wrong code fails the GCM tag",
    );
});

test("sync copies: text and bytes roundtrip after unlocking", async () => {
    const salt = btoa("0123456789abcdef");
    const key = deriveWrapKeyFromCode("ROUNDTRIP9", salt);
    const nonce = new Uint8Array(12).fill(3);
    const secret = new Uint8Array(32).fill(5);
    const data = gcm(key, nonce).encrypt(secret);

    await signalKeyStore.saveSyncSecret(
        btoa(String.fromCharCode(...secret)),
    );

    const env = await encryptSyncText("hello from the account", "cipher-fp");
    assert.equal(env.ciphertext, "cipher-fp");
    assert.equal(
        await decryptSyncText(env),
        "hello from the account",
    );

    const bytes = new Uint8Array([1, 2, 3, 4, 5]);
    const blob = await encryptSyncBytes(bytes);
    assert.deepEqual(
        await decryptSyncBytes(blob),
        bytes,
    );

    // Tampered data must not decrypt.
    const tampered = { ...env, data: "AAAA" + env.data.slice(4) };
    assert.equal(
        await decryptSyncText(tampered),
        null,
    );
});

test("sync copies without a stored secret return null", async () => {
    await signalKeyStore.saveSyncSecret("");
    clearSyncKeyCache();
    const env = { nonce: "AAAA", data: "BBBB" };
    assert.equal(await encryptSyncText("x"), null);
    assert.equal(await decryptSyncText(env), null);
    assert.equal(await decryptSyncBytes(env), null);
});