// ==========================================================
// IndexedDB Encryption Layer
//
// Encrypts all sensitive data before storing in IndexedDB using
// AES-256-GCM with a key derived from user's passphrase via PBKDF2.
// ==========================================================

import { randomBytes } from "./signal/bytes.js";

const PBKDF2_ITERATIONS = 600_000;
const KEY_LENGTH = 32;
const NONCE_SIZE = 12;
const SALT_SIZE = 16;

let _encryptionKey = null;
let _salt = null;

/**
 * Derive encryption key from passphrase using PBKDF2
 */
export async function deriveEncryptionKey(passphrase, salt = null) {
    const encoder = new TextEncoder();
    const passphraseBuffer = encoder.encode(passphrase);
    
    if (!salt) {
        salt = randomBytes(SALT_SIZE);
    } else if (typeof salt === 'string') {
        salt = Uint8Array.from(atob(salt), c => c.charCodeAt(0));
    }
    
    const keyMaterial = await crypto.subtle.importKey(
        'raw',
        passphraseBuffer,
        'PBKDF2',
        false,
        ['deriveBits']
    );
    
    const derivedBits = await crypto.subtle.deriveBits(
        {
            name: 'PBKDF2',
            salt,
            iterations: PBKDF2_ITERATIONS,
            hash: 'SHA-256'
        },
        keyMaterial,
        KEY_LENGTH * 8
    );
    
    const key = await crypto.subtle.importKey(
        'raw',
        derivedBits,
        'AES-GCM',
        false,
        ['encrypt', 'decrypt']
    );
    
    return { key, salt };
}

/**
 * Set the encryption key for the current session
 */
export async function setEncryptionKey(passphrase, salt = null) {
    const { key, salt: derivedSalt } = await deriveEncryptionKey(passphrase, salt);
    _encryptionKey = key;
    _salt = derivedSalt;
    return btoa(String.fromCharCode(...new Uint8Array(derivedSalt)));
}

/**
 * Get the current salt (base64 encoded)
 */
export function getSalt() {
    if (!_salt) return null;
    return btoa(String.fromCharCode(...new Uint8Array(_salt)));
}

/**
 * Check if encryption key is set
 */
export function hasEncryptionKey() {
    return _encryptionKey !== null;
}

/**
 * Clear the encryption key (on logout)
 */
export function clearEncryptionKey() {
    _encryptionKey = null;
    _salt = null;
}

/**
 * Encrypt data before storing in IndexedDB
 */
export async function encryptForStorage(data) {
    if (!_encryptionKey) {
        throw new Error('Encryption key not set. Call setEncryptionKey() first.');
    }
    
    const encoder = new TextEncoder();
    const plaintext = encoder.encode(JSON.stringify(data));
    const nonce = randomBytes(NONCE_SIZE);
    
    const ciphertext = await crypto.subtle.encrypt(
        { name: 'AES-GCM', nonce },
        _encryptionKey,
        plaintext
    );
    
    return {
        v: 1, // version
        s: btoa(String.fromCharCode(...new Uint8Array(_salt))),
        n: btoa(String.fromCharCode(...nonce)),
        c: btoa(String.fromCharCode(...new Uint8Array(ciphertext)))
    };
}

/**
 * Decrypt data retrieved from IndexedDB
 */
export async function decryptFromStorage(encryptedData) {
    if (!_encryptionKey) {
        throw new Error('Encryption key not set. Call setEncryptionKey() first.');
    }
    
    if (!encryptedData || typeof encryptedData !== 'object') {
        // Legacy unencrypted data - return as-is for migration
        return encryptedData;
    }
    
    if (encryptedData.v !== 1) {
        throw new Error(`Unknown encryption version: ${encryptedData.v}`);
    }
    
    const salt = Uint8Array.from(atob(encryptedData.s), c => c.charCodeAt(0));
    const nonce = Uint8Array.from(atob(encryptedData.n), c => c.charCodeAt(0));
    const ciphertext = Uint8Array.from(atob(encryptedData.c), c => c.charCodeAt(0));
    
    // Verify salt matches current key
    const currentSalt = new Uint8Array(_salt);
    if (salt.length !== currentSalt.length || !salt.every((v, i) => v === currentSalt[i])) {
        throw new Error('Salt mismatch - wrong passphrase or corrupted data');
    }
    
    const plaintext = await crypto.subtle.decrypt(
        { name: 'AES-GCM', nonce },
        _encryptionKey,
        ciphertext
    );
    
    const decoder = new TextDecoder();
    return JSON.parse(decoder.decode(plaintext));
}

/**
 * Migrate unencrypted data to encrypted format
 */
export async function migrateToEncrypted(store, getAllFn, putFn) {
    if (!_encryptionKey) return;
    
    const allRecords = await getAllFn(store);
    for (const record of allRecords) {
        // Check if already encrypted (has version field)
        if (record && record.v === 1) continue;
        
        const encrypted = await encryptForStorage(record);
        await putFn(store, record.id || record.keyId || record.id, encrypted);
    }
}