// ==========================================================
// CipherChat Key Storage
//
// Stores RSA keys in browser.
//
// Development:
// LocalStorage
//
// Production:
// IndexedDB
// ==========================================================

const PUBLIC_KEY = "cipherchat_public_key";
const PRIVATE_KEY = "cipherchat_private_key";

// ==========================================================
// Save Public Key
// ==========================================================

export function savePublicKey(
    key
) {

    localStorage.setItem(
        PUBLIC_KEY,
        key
    );

}

// ==========================================================
// Save Private Key
// ==========================================================

export function savePrivateKey(
    key
) {

    localStorage.setItem(
        PRIVATE_KEY,
        key
    );

}

// ==========================================================
// Get Public Key
// ==========================================================

export function getPublicKey() {

    return localStorage.getItem(
        PUBLIC_KEY
    );

}

// ==========================================================
// Get Private Key
// ==========================================================

export function getPrivateKey() {

    return localStorage.getItem(
        PRIVATE_KEY
    );

}

// ==========================================================
// Save Both Keys
// ==========================================================

export function saveKeyPair(
    publicKey,
    privateKey
) {

    savePublicKey(
        publicKey
    );

    savePrivateKey(
        privateKey
    );

}

// ==========================================================
// Load Both Keys
// ==========================================================

export function loadKeyPair() {

    return {

        publicKey:
            getPublicKey(),

        privateKey:
            getPrivateKey(),

    };

}

// ==========================================================
// Keys Exist
// ==========================================================

export function hasKeyPair() {

    return !!(

        getPublicKey()

        &&

        getPrivateKey()

    );

}

// ==========================================================
// Remove Keys
// ==========================================================

export function clearKeyPair() {

    localStorage.removeItem(
        PUBLIC_KEY
    );

    localStorage.removeItem(
        PRIVATE_KEY
    );

}