// ==========================================================
// One-Time PreKey manager tests (Node + fake-indexeddb)
// Run: node --test tests/signal/
// ==========================================================

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "fake-indexeddb/auto";

import { SignalKeyStore } from "../../src/crypto/signal/keyStore.js";
import { replenishOneTimePrekeys } from "../../src/crypto/signal/prekeyManager.js";

let store;
let uploads;

beforeEach(async () => {
    store = new SignalKeyStore("test-replenish");
    await store.clearAll();
    uploads = [];
});

function noopUpload(payload) {
    uploads.push(payload);
    return payload;
}

test("replenishes when the pool is below the threshold", async () => {
    const result = await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 3,
        batchSize: 5,
        upload: noopUpload,
    });

    assert.equal(result.replenished, 5);
    assert.equal(result.count, 5);
    assert.equal(result.uploaded, 5);
    assert.equal(await store.getOneTimePrekeyCount(), 5);

    // Uploaded payload matches the local keys
    const local = await store.getAllOneTimePrekeys();
    assert.equal(uploads.length, 1);
    assert.equal(uploads[0].length, 5);
    assert.equal(uploads[0][0].key_id, local[0].keyId);
    assert.equal(uploads[0][0].public_key, local[0].publicKey);
});

test("does nothing while the pool is healthy", async () => {
    await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 3,
        batchSize: 5,
        upload: noopUpload,
    });
    uploads.length = 0;

    const result = await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 3,
        batchSize: 5,
        upload: noopUpload,
    });

    assert.equal(result.replenished, 0);
    assert.equal(result.uploaded, 0);
    assert.equal(uploads.length, 0);
    assert.equal(await store.getOneTimePrekeyCount(), 5);
});

test("continues key numbering after partial consumption", async () => {
    await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 2,
        batchSize: 5,
        upload: noopUpload,
    });

    // Consume four: pool 5 -> 1 (below threshold)
    const local = await store.getAllOneTimePrekeys();
    for (const opk of local.slice(0, 4)) {
        await store.removeOneTimePrekey(opk.keyId);
    }
    assert.equal(await store.getOneTimePrekeyCount(), 1);

    const result = await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 3,
        batchSize: 5,
        upload: noopUpload,
    });

    assert.equal(result.replenished, 5);
    assert.equal(uploads.at(-1)[0].key_id, 6); // ids continue past 5
    assert.equal(await store.getOneTimePrekeyCount(), 6);

    // No duplicate private keys ever stored
    const keys = (await store.getAllOneTimePrekeys())
        .flatMap((opk) => [opk.privateKey]);
    assert.equal(new Set(keys).size, keys.length);
});

test("keeps local keys even when the upload fails", async () => {
    const result = await replenishOneTimePrekeys({
        keyStore: store,
        threshold: 3,
        batchSize: 5,
        upload: () => { throw new Error("network down"); },
    });

    assert.equal(result.replenished, 5);
    assert.equal(result.uploaded, 0);
    assert.equal(await store.getOneTimePrekeyCount(), 5);
});

test("empty pool with no registered device is a no-op", async () => {
    const result = await replenishOneTimePrekeys({
        keyStore: new SignalKeyStore("test-empty"),
        threshold: 3,
        batchSize: 5,
        upload: noopUpload,
    });

    assert.equal(result.replenished, 5);
    assert.equal(uploads.length, 1);
});