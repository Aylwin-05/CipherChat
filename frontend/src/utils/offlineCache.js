const DB_NAME = "nexara-offline";
const DB_VERSION = 1;
const STORE_MESSAGES = "messages";
const STORE_QUEUE = "outbox";

function openDB() {
    return new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
            const db = req.result;
            if (!db.objectStoreNames.contains(STORE_MESSAGES)) {
                const store = db.createObjectStore(STORE_MESSAGES, { keyPath: "id" });
                store.createIndex("conversation_id", "conversation_id", { unique: false });
                store.createIndex("created_at", "created_at", { unique: false });
            }
            if (!db.objectStoreNames.contains(STORE_QUEUE)) {
                db.createObjectStore(STORE_QUEUE, { keyPath: "id", autoIncrement: true });
            }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}

// ==========================================================
// Message cache (IndexedDB)
// ==========================================================

export async function cacheMessage(message) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_MESSAGES, "readwrite");
        tx.objectStore(STORE_MESSAGES).put(message);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

export async function cacheMessages(messages) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_MESSAGES, "readwrite");
        const store = tx.objectStore(STORE_MESSAGES);
        for (const msg of messages) {
            store.put(msg);
        }
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

export async function getCachedMessages(conversationId, limit = 100) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_MESSAGES, "readonly");
        const idx = tx.objectStore(STORE_MESSAGES).index("conversation_id");
        const req = idx.getAll(conversationId);
        req.onsuccess = () => {
            const all = req.result.sort(
                (a, b) => new Date(b.created_at) - new Date(a.created_at)
            );
            resolve(all.slice(0, limit));
        };
        req.onerror = () => reject(req.error);
    });
}

export async function deleteCachedMessage(messageId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_MESSAGES, "readwrite");
        tx.objectStore(STORE_MESSAGES).delete(messageId);
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

export async function clearCachedMessages(conversationId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_MESSAGES, "readwrite");
        const idx = tx.objectStore(STORE_MESSAGES).index("conversation_id");
        const req = idx.openCursor(conversationId);
        req.onsuccess = () => {
            const cursor = req.result;
            if (cursor) {
                cursor.delete();
                cursor.continue();
            }
        };
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

// ==========================================================
// Offline outbox queue (messages sent while offline)
// ==========================================================

export async function enqueueMessage(payload) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_QUEUE, "readwrite");
        tx.objectStore(STORE_QUEUE).add({
            ...payload,
            queued_at: new Date().toISOString(),
        });
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

export async function dequeueMessages() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_QUEUE, "readwrite");
        const store = tx.objectStore(STORE_QUEUE);
        const req = store.getAll();
        req.onsuccess = () => {
            const items = req.result;
            store.clear();
            resolve(items);
        };
        tx.onerror = () => reject(tx.error);
    });
}

export async function getQueueSize() {
    const db = await openDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_QUEUE, "readonly");
        const req = tx.objectStore(STORE_QUEUE).count();
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
    });
}
