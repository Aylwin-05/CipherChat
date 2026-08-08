// ==========================================================
// CipherChat Signal Key Store (IndexedDB)
//
// Persists the device's Signal identity material, one-time
// prekeys and ratchet session states in a browser IndexedDB.
//
//   - "identity":         Ed25519 keys + derived X25519 identity
//   - "signed_prekey":    current signed prekey (client-owned)
//   - "one_time_prekeys": local pool of OPK privates
//   - "sessions":         double-ratchet session states
//   - "meta":             device info / storage secrets
//
// All values are base64 strings (the raw bytes live at the JS
// layer only). In a hardened product these records would be
// additionally encrypted with a passphrase-derived key; the
// IndexedDB layer keeps that boundary simple for now.
// ==========================================================

const DB_NAME = "cipherchat-signal";
const DB_VERSION = 1;

const STORE_IDENTITY = "identity";
const STORE_SIGNED_PREKEY = "signed_prekey";
const STORE_ONE_TIME_PREKEYS = "one_time_prekeys";
const STORE_SESSIONS = "sessions";
const STORE_META = "meta";

function openDb(dbName) {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(dbName, DB_VERSION);
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains(STORE_SIGNED_PREKEY)) {
                db.createObjectStore(STORE_SIGNED_PREKEY, { keyPath: "keyId" });
            }
            if (!db.objectStoreNames.contains(STORE_ONE_TIME_PREKEYS)) {
                db.createObjectStore(STORE_ONE_TIME_PREKEYS, { keyPath: "keyId" });
            }
            if (!db.objectStoreNames.contains(STORE_SESSIONS)) {
                db.createObjectStore(STORE_SESSIONS, { keyPath: "id" });
            }
            if (!db.objectStoreNames.contains(STORE_IDENTITY)) {
                db.createObjectStore(STORE_IDENTITY, { keyPath: "id" });
            }
            if (!db.objectStoreNames.contains(STORE_META)) {
                db.createObjectStore(STORE_META, { keyPath: "id" });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

function tx(db, storeName, mode) {
    return db.transaction(storeName, mode).objectStore(storeName);
}

function promisify(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// ==========================================================
// Key Store
// ==========================================================

export class SignalKeyStore {
    constructor(dbName = DB_NAME) {
        this._dbName = dbName;
        this._dbPromise = null;
    }

    async _db() {
        if (!this._dbPromise) {
            this._dbPromise = openDb(this._dbName);
        }
        return this._dbPromise;
    }

    // ------------------------------------------------------
    // Meta (device record)
    // ------------------------------------------------------

    async saveMeta(meta) {
        const db = await this._db();
        await promisify(tx(db, STORE_META, "readwrite").put({
            id: meta.id ?? "device",
            ...meta,
        }));
    }

    async getMeta() {
        const db = await this._db();
        const record = await promisify(tx(db, STORE_META, "readonly").get("device"));
        return record ?? null;
    }

    async peekMeta(id) {
        const db = await this._db();
        const record = await promisify(tx(db, STORE_META, "readonly").get(id));
        return record ?? null;
    }

    async clearMeta() {
        const db = await this._db();
        await promisify(tx(db, STORE_META, "readwrite").delete("device"));
    }

    // ------------------------------------------------------
    // Identity keys
    // ------------------------------------------------------

    async saveIdentity(identity) {
        const db = await this._db();
        const store = tx(db, STORE_IDENTITY, "readwrite");
        await promisify(store.put({
            id: "device",
            deviceId: identity.deviceId,
            identityKeyPrivate: identity.identityKeyPrivate,       // b64 Ed25519 priv
            identityKeyPublic: identity.identityKeyPublic,       // b64 Ed25519 pub
            x25519IdentityKeyPublic: identity.x25519IdentityKeyPublic, // b64 X25519 pub
            createdAt: Date.now(),
        }));
    }

    async getIdentity() {
        const db = await this._db();
        const record = await promisify(tx(db, STORE_IDENTITY, "readonly").get("device"));
        return record ?? null;
    }

    // ------------------------------------------------------
    // Signed prekey (only the latest is kept)
    // ------------------------------------------------------

    async saveSignedPrekey(spk) {
        const db = await this._db();
        const store = tx(db, STORE_SIGNED_PREKEY, "readwrite");
        await promisify(store.put({
            keyId: spk.keyId,
            publicKey: spk.publicKey,       // b64
            signature: spk.signature,       // b64
            privateKey: spk.privateKey,     // b64
        }));
    }

    async getAllSignedPrekeys() {
        const db = await this._db();
        return await promisify(tx(db, STORE_SIGNED_PREKEY, "readonly").getAll());
    }

    async getSignedPrekey(keyId) {
        const db = await this._db();
        return await promisify(tx(db, STORE_SIGNED_PREKEY, "readonly").get(keyId));
    }

    async clearSignedPrekeys() {
        const db = await this._db();
        await promisify(tx(db, STORE_SIGNED_PREKEY, "readwrite").clear());
    }

    // ------------------------------------------------------
    // One-time prekeys (local private pool)
    // ------------------------------------------------------

    async saveOneTimePrekeys(opks) {
        const db = await this._db();
        const store = tx(db, STORE_ONE_TIME_PREKEYS, "readwrite");
        for (const opk of opks) {
            await promisify(store.put({
                keyId: opk.keyId,
                publicKey: opk.publicKey,
                privateKey: opk.privateKey,
            }));
        }
    }

    async getAllOneTimePrekeys() {
        const db = await this._db();
        return await promisify(tx(db, STORE_ONE_TIME_PREKEYS, "readonly").getAll());
    }

    async getOneTimePrekey(keyId) {
        const db = await this._db();
        return await promisify(tx(db, STORE_ONE_TIME_PREKEYS, "readonly").get(keyId));
    }

    async getOneTimePrekeyCount() {
        const db = await this._db();
        const count = await promisify(
            tx(db, STORE_ONE_TIME_PREKEYS, "readonly").count(),
        );
        return count;
    }

    async removeOneTimePrekey(keyId) {
        const db = await this._db();
        await promisify(tx(db, STORE_ONE_TIME_PREKEYS, "readwrite").delete(keyId));
    }

    async clearOneTimePrekeys() {
        const db = await this._db();
        await promisify(tx(db, STORE_ONE_TIME_PREKEYS, "readwrite").clear());
    }

    // ------------------------------------------------------
    // Double-ratchet sessions (keyed by conversation/devices)
    // ------------------------------------------------------

    async saveSession({ ourDeviceId, remoteDeviceId, conversationId }, state) {
        const db = await this._db();
        const store = tx(db, STORE_SESSIONS, "readwrite");
        await promisify(store.put({
            id: sessionId(ourDeviceId, remoteDeviceId, conversationId),
            ourDeviceId,
            remoteDeviceId,
            conversationId,
            state,
        }));
    }

    async getSession({ ourDeviceId, remoteDeviceId, conversationId }) {
        const db = await this._db();
        const record = await promisify(
            tx(db, STORE_SESSIONS, "readonly")
                .get(sessionId(ourDeviceId, remoteDeviceId, conversationId)),
        );
        return record ? record.state : null;
    }

    async deleteSession({ ourDeviceId, remoteDeviceId, conversationId }) {
        const db = await this._db();
        await promisify(
            tx(db, STORE_SESSIONS, "readwrite")
                .delete(sessionId(ourDeviceId, remoteDeviceId, conversationId)),
        );
    }

    // ------------------------------------------------------
    // Wipe everything (logout / re-registration)
    // ------------------------------------------------------

    async clearAll() {
        const db = await this._db();
        const t = db.transaction(
            [STORE_IDENTITY, STORE_ONE_TIME_PREKEYS, STORE_SESSIONS, STORE_SIGNED_PREKEY, STORE_META],
            "readwrite",
        );
        await Promise.all(
            [STORE_IDENTITY, STORE_ONE_TIME_PREKEYS, STORE_SESSIONS, STORE_SIGNED_PREKEY, STORE_META]
                .map((name) => promisify(t.objectStore(name).clear())),
        );
    }
}

function sessionId(ourDeviceId, remoteDeviceId, conversationId) {
    return `${ourDeviceId}|${remoteDeviceId}|${conversationId}`;
}

// Singleton used across the app
export const signalKeyStore = new SignalKeyStore();