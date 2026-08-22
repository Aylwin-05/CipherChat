// ==========================================================
// CipherChat One-Time PreKey Manager
//
// The client owns the private halves of every one-time prekey
// (they must live in the local key store so this device can
// decrypt X3DH handshakes addressed to it). This module keeps
// the local pool topped up and mirrors the generated batch to
// the server so peers can initiate new sessions.
//
// Pure logic: the upload callback is injected so the module
// stays runnable under node --test.
// ==========================================================

import { signalKeyStore } from "./keyStore.js";
import { generateOneTimePrekeys } from "./identity.js";
import { b64encode } from "./bytes.js";

export const DEFAULT_THRESHOLD = 20;
export const DEFAULT_BATCH_SIZE = 100;

// ==========================================================
// Replenish the local one-time prekey pool if it runs low
// ==========================================================

export async function replenishOneTimePrekeys({
    keyStore = signalKeyStore,
    threshold = DEFAULT_THRESHOLD,
    batchSize = DEFAULT_BATCH_SIZE,
    upload = null,
} = {}) {
    const count = await keyStore.getOneTimePrekeyCount();

    if (count >= threshold) {
        return {
            replenished: 0,
            count,
            uploaded: 0,
        };
    }

    const existing = await keyStore.getAllOneTimePrekeys();
    const nextId =
        existing.reduce(
            (max, prekey) => Math.max(max, prekey.keyId),
            0,
        ) + 1;

    const generated = generateOneTimePrekeys({
        startId: nextId,
        count: batchSize,
    });

    const local = generated.map((opk) => ({
        keyId: opk.keyId,
        publicKey: b64encode(opk.publicKey),
        privateKey: b64encode(opk.privateKey),
    }));

    // Persist locally FIRST so the device can always decrypt
    // handshakes even if the upload below fails.
    await keyStore.saveOneTimePrekeys(local);

    let uploaded = 0;
    if (upload) {
        const payload = generated.map((opk) => ({
            key_id: opk.keyId,
            public_key: b64encode(opk.publicKey),
        }));
        try {
            await upload(payload);
            uploaded = payload.length;
        } catch {
            // Non-fatal: next replenish attempt retries the upload.
        }
    }

    return {
        replenished: local.length,
        count: count + local.length,
        uploaded,
    };
}