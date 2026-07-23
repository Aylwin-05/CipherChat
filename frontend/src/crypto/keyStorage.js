// ==========================================================
// CipherChat Key Storage
//
// Stores user's RSA key pair in browser.
//
// NOTE:
// For production, use IndexedDB.
// LocalStorage is used during development.
// ==========================================================

const PUBLIC_KEY = "cipherchat_public_key";
const PRIVATE_KEY = "cipherchat_private_key";

// ==========================================================
// Save Keys
// ==========================================================

export function saveKeyPair(
    publicKey,
    privateKey
) {

    localStorage.setItem(
        PUBLIC_KEY,
        publicKey
    );

    localStorage.setItem(
        PRIVATE_KEY,
        privateKey
    );

}

// ==========================================================
// Load Keys
// ==========================================================

export function loadKeyPair() {

    return {

        publicKey:
            localStorage.getItem(
                PUBLIC_KEY
            ),

        privateKey:
            localStorage.getItem(
                PRIVATE_KEY
            ),

    };

}

// ==========================================================
// Check if Keys Exist
// ==========================================================

export function hasKeyPair() {

    return !!(
        localStorage.getItem(PUBLIC_KEY)
        &&
        localStorage.getItem(PRIVATE_KEY)
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