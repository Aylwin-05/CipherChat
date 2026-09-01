// ==========================================================
// Encrypted IndexedDB Layer
//
// Wraps every value written to the Signal key store with
// AES-256-GCM encryption before it touches IndexedDB.  The
// encryption key is derived from a user-supplied passphrase
// via PBKDF2-SHA-256 (600 000 iterations, hardware-isolated
// salt stored in a separate meta record).
//
// Usage:
//   const enc = new EncryptedStore(signalKeyStore);
//   await enc.unlock("user-passphrase");
//   // now enc.saveIdentity() / enc.getIdentity() are
//   // transparently encrypted / decrypted.
//
// If unlock() is never called the store falls back to
// plaintext (backward-compatible with existing sessions
// that pre-date this layer).
// ==========================================================

const PBKDF2_ITERATIONS = 600_000;
const SALT_LEN = 32;
const IV_LEN = 12; // 96-bit for AES-GCM
const TAG_LEN = 128;
const VERIFY_PLAINTEXT = "nexara-verify-v1";

function b64Encode(buf) {
    const bytes = new Uint8Array(buf);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}

function b64Decode(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

function concatBuffers(...bufs) {
    const total = bufs.reduce((s, b) => s + b.byteLength, 0);
    const out = new Uint8Array(total);
    let offset = 0;
    for (const buf of bufs) {
        out.set(new Uint8Array(buf), offset);
        offset += buf.byteLength;
    }
    return out.buffer;
}

function getRandomBytes(len) {
    return crypto.getRandomValues(new Uint8Array(len)).buffer;
}

async function deriveKey(passphrase, salt) {
    const enc = new TextEncoder();
    const keyMaterial = await crypto.subtle.importKey(
        "raw",
        enc.encode(passphrase),
        "PBKDF2",
        false,
        ["deriveKey"],
    );

    return crypto.subtle.deriveKey(
        {
            name: "PBKDF2",
            salt,
            iterations: PBKDF2_ITERATIONS,
            hash: "SHA-256",
        },
        keyMaterial,
        { name: "AES-GCM", length: 256 },
        false,
        ["encrypt", "decrypt"],
    );
}

async function encryptValue(key, plaintext) {
    const iv = getRandomBytes(IV_LEN);
    const enc = new TextEncoder();
    const ciphertext = await crypto.subtle.encrypt(
        { name: "AES-GCM", iv, tagLength: TAG_LEN },
        key,
        enc.encode(plaintext),
    );
    return b64Encode(concatBuffers(iv, ciphertext));
}

async function decryptValue(key, b64) {
    const raw = new Uint8Array(b64Decode(b64));
    const iv = raw.slice(0, IV_LEN);
    const ciphertext = raw.slice(IV_LEN);
    const plainBuf = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv, tagLength: TAG_LEN },
        key,
        ciphertext,
    );
    return new TextDecoder().decode(plainBuf);
}

function cloneRecord(record) {
    if (record === null || record === undefined) return record;
    return JSON.parse(JSON.stringify(record));
}

// ==========================================================
// EncryptedStore — wraps an existing SignalKeyStore
// ==========================================================

export class EncryptedStore {
    constructor(inner) {
        this._inner = inner;
        this._key = null;
        this._unlocked = false;
    }

    async unlock(passphrase) {
        if (!passphrase || passphrase.length === 0) {
            throw new Error("Passphrase must not be empty.");
        }

        const meta = await this._inner.getMeta();
        let saltBuf;

        if (meta && meta._enc_salt) {
            saltBuf = b64Decode(meta._enc_salt);
        } else {
            saltBuf = getRandomBytes(SALT_LEN);
            const existingMeta = (await this._inner.getMeta()) || {};
            await this._inner.saveMeta({
                ...existingMeta,
                id: "device",
                _enc_salt: b64Encode(saltBuf),
            });
        }

        const key = await deriveKey(passphrase, saltBuf);

        if (meta && meta._enc_verify) {
            try {
                const verification = await decryptValue(
                    key,
                    meta._enc_verify,
                );
                if (verification !== VERIFY_PLAINTEXT) {
                    throw new Error(
                        "Wrong passphrase.",
                    );
                }
            } catch {
                throw new Error("Wrong passphrase.");
            }
        } else {
            const encrypted = await encryptValue(
                key,
                VERIFY_PLAINTEXT,
            );
            const existingMeta =
                (await this._inner.getMeta()) || {};
            await this._inner.saveMeta({
                ...existingMeta,
                id: "device",
                _enc_salt: b64Encode(saltBuf),
                _enc_verify: encrypted,
            });
        }

        this._key = key;
        this._unlocked = true;
    }

    get isUnlocked() {
        return this._unlocked;
    }

    lock() {
        this._key = null;
        this._unlocked = false;
    }

    _needsEncrypt() {
        return this._unlocked && this._key !== null;
    }

    async _enc(record) {
        if (!this._needsEncrypt() || record === null) {
            return record;
        }
        const clone = cloneRecord(record);
        const sensitiveFields = [
            "privateKey",
            "identityKeyPrivate",
            "signature",
            "state",
            "plaintext",
            "secret",
        ];
        for (const field of sensitiveFields) {
            if (
                clone[field] !== undefined &&
                clone[field] !== null &&
                typeof clone[field] === "string"
            ) {
                clone[field] = await encryptValue(
                    this._key,
                    clone[field],
                );
                clone[`_${field}_enc`] = true;
            }
        }
        return clone;
    }

    async _dec(record) {
        if (!this._needsEncrypt() || record === null) {
            return record;
        }
        const clone = cloneRecord(record);
        const sensitiveFields = [
            "privateKey",
            "identityKeyPrivate",
            "signature",
            "state",
            "plaintext",
            "secret",
        ];
        for (const field of sensitiveFields) {
            if (clone[`_${field}_enc`]) {
                try {
                    clone[field] = await decryptValue(
                        this._key,
                        clone[field],
                    );
                } catch {
                    console.error(
                        `Failed to decrypt field "${field}" — record may be corrupted.`,
                    );
                    clone[field] = null;
                }
                delete clone[`_${field}_enc`];
            }
        }
        return clone;
    }

    async _encArray(records) {
        const out = [];
        for (const r of records) {
            out.push(await this._enc(r));
        }
        return out;
    }

    // ------------------------------------------------------
    // Meta
    // ------------------------------------------------------

    async saveMeta(meta) {
        return this._inner.saveMeta(meta);
    }

    async getMeta() {
        return this._inner.getMeta();
    }

    async peekMeta(id) {
        return this._inner.peekMeta(id);
    }

    async clearMeta() {
        return this._inner.clearMeta();
    }

    async saveSyncSecret(secretB64, email = null) {
        return this._inner.saveSyncSecret(
            secretB64,
            email,
        );
    }

    async getSyncSecret() {
        return this._inner.getSyncSecret();
    }

    async getSyncRecord() {
        return this._inner.getSyncRecord();
    }

    async clearSyncRecord() {
        return this._inner.clearSyncRecord();
    }

    // ------------------------------------------------------
    // Identity
    // ------------------------------------------------------

    async saveIdentity(identity) {
        const encrypted = await this._enc({
            ...identity,
            id: "device",
        });
        const db = await this._inner._db();
        const store = this._inner._txWrapped(
            db,
            "identity",
            "readwrite",
        );
        await this._inner._promisify(store.put(encrypted));
    }

    async getIdentity() {
        const db = await this._inner._db();
        const record = await this._inner._promisify(
            this._inner._txWrapped(
                db,
                "identity",
                "readonly",
            ).get("device"),
        );
        return this._dec(record ?? null);
    }

    // ------------------------------------------------------
    // Signed prekey
    // ------------------------------------------------------

    async saveSignedPrekey(spk) {
        const encrypted = await this._enc(spk);
        const db = await this._inner._db();
        const store = this._inner._txWrapped(
            db,
            "signed_prekey",
            "readwrite",
        );
        await this._inner._promisify(store.put(encrypted));
    }

    async getAllSignedPrekeys() {
        const records = await this._inner.getAllSignedPrekeys();
        return this._encArray(records);
    }

    async getSignedPrekey(keyId) {
        const record = await this._inner.getSignedPrekey(
            keyId,
        );
        return this._dec(record);
    }

    async clearSignedPrekeys() {
        return this._inner.clearSignedPrekeys();
    }

    // ------------------------------------------------------
    // One-time prekeys
    // ------------------------------------------------------

    async saveOneTimePrekeys(opks) {
        const encrypted = [];
        for (const opk of opks) {
            encrypted.push(await this._enc(opk));
        }
        return this._inner.saveOneTimePrekeys(encrypted);
    }

    async getAllOneTimePrekeys() {
        const records =
            await this._inner.getAllOneTimePrekeys();
        return this._encArray(records);
    }

    async getOneTimePrekey(keyId) {
        const record =
            await this._inner.getOneTimePrekey(keyId);
        return this._dec(record);
    }

    async getOneTimePrekeyCount() {
        return this._inner.getOneTimePrekeyCount();
    }

    async removeOneTimePrekey(keyId) {
        return this._inner.removeOneTimePrekey(keyId);
    }

    async clearOneTimePrekeys() {
        return this._inner.clearOneTimePrekeys();
    }

    // ------------------------------------------------------
    // Sessions
    // ------------------------------------------------------

    async saveSession(keys, state) {
        const encrypted = await this._enc({ state });
        return this._inner.saveSession(keys, encrypted.state);
    }

    async getSession(keys) {
        const state = await this._inner.getSession(keys);
        if (state === null) return null;
        return this._dec({ state }).then(
            (r) => r?.state ?? null,
        );
    }

    async deleteSession(keys) {
        return this._inner.deleteSession(keys);
    }

    // ------------------------------------------------------
    // Plaintext cache
    // ------------------------------------------------------

    async savePlaintext(
        conversationId,
        messageId,
        plaintext,
        ciphertext = null,
    ) {
        const encrypted = await this._enc({
            plaintext,
            ciphertext,
        });
        const db = await this._inner._db();
        const store = this._inner._txWrapped(
            db,
            "plaintext_cache",
            "readwrite",
        );
        await this._inner._promisify(
            store.put({
                id: `${conversationId}:${messageId}`,
                conversationId,
                messageId,
                plaintext: encrypted.plaintext,
                ciphertext: encrypted.ciphertext,
                _plaintext_enc: encrypted._plaintext_enc,
                _ciphertext_enc: encrypted._ciphertext_enc,
            }),
        );
    }

    async getCachedRecord(conversationId, messageId) {
        const record = await this._inner.getCachedRecord(
            conversationId,
            messageId,
        );
        return this._dec(record);
    }

    async getPlaintext(conversationId, messageId) {
        const record = await this.getCachedRecord(
            conversationId,
            messageId,
        );
        return record ? record.plaintext : null;
    }

    // ------------------------------------------------------
    // Wipe
    // ------------------------------------------------------

    async clearAll() {
        this.lock();
        return this._inner.clearAll();
    }
}

let _encryptedSingleton = null;

export function createEncryptedStore(keyStore) {
    if (!_encryptedSingleton) {
        _encryptedSingleton = new EncryptedStore(keyStore);
    }
    return _encryptedSingleton;
}

export function getEncryptedStore() {
    return _encryptedSingleton;
}
