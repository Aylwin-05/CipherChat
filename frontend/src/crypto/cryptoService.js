// ==========================================================
// CipherChat Crypto Service
//
// Uses:
//
// RSA-OAEP (2048)
// AES-GCM (256)
// Web Crypto API
//
// Backend NEVER decrypts messages.
// ==========================================================

import {
    arrayBufferToBase64,
    base64ToArrayBuffer,
} from "./base64";

// ==========================================================
// Generate RSA Key Pair
// ==========================================================

export async function generateKeyPair() {

    return await window.crypto.subtle.generateKey(
        {
            name: "RSA-OAEP",
            modulusLength: 2048,
            publicExponent: new Uint8Array([
                1,
                0,
                1,
            ]),
            hash: "SHA-256",
        },
        true,
        [
            "encrypt",
            "decrypt",
        ]
    );

}

// ==========================================================
// Export Public Key
// ==========================================================

export async function exportPublicKey(
    publicKey
) {

    const key =
        await crypto.subtle.exportKey(
            "spki",
            publicKey
        );

    return arrayBufferToBase64(key);

}

// ==========================================================
// Export Private Key
// ==========================================================

export async function exportPrivateKey(
    privateKey
) {

    const key =
        await crypto.subtle.exportKey(
            "pkcs8",
            privateKey
        );

    return arrayBufferToBase64(key);

}

// ==========================================================
// Import Public Key
// ==========================================================

export async function importPublicKey(
    base64
) {

    return await crypto.subtle.importKey(
        "spki",
        base64ToArrayBuffer(base64),
        {
            name: "RSA-OAEP",
            hash: "SHA-256",
        },
        true,
        [
            "encrypt",
        ]
    );

}

// ==========================================================
// Import Private Key
// ==========================================================

export async function importPrivateKey(
    base64
) {

    return await crypto.subtle.importKey(
        "pkcs8",
        base64ToArrayBuffer(base64),
        {
            name: "RSA-OAEP",
            hash: "SHA-256",
        },
        true,
        [
            "decrypt",
        ]
    );

}

// ==========================================================
// Generate AES Key
// ==========================================================

export async function generateAESKey() {

    return await crypto.subtle.generateKey(
        {
            name: "AES-GCM",
            length: 256,
        },
        true,
        [
            "encrypt",
            "decrypt",
        ]
    );

}

// ==========================================================
// Encrypt Plaintext
// ==========================================================

export async function encryptMessage(
    plaintext,
    recipientPublicKey
) {

    const aesKey =
        await generateAESKey();

    const iv =
        crypto.getRandomValues(
            new Uint8Array(12)
        );

    const encoder =
        new TextEncoder();

    const ciphertext =
        await crypto.subtle.encrypt(
            {
                name: "AES-GCM",
                iv,
            },
            aesKey,
            encoder.encode(
                plaintext
            )
        );

    const exportedAES =
        await crypto.subtle.exportKey(
            "raw",
            aesKey
        );

    const encryptedAES =
        await crypto.subtle.encrypt(
            {
                name: "RSA-OAEP",
            },
            recipientPublicKey,
            exportedAES
        );

    return {

        ciphertext:
            arrayBufferToBase64(
                ciphertext
            ),

        encrypted_key:
            arrayBufferToBase64(
                encryptedAES
            ),

        nonce:
            arrayBufferToBase64(
                iv.buffer
            ),

    };

}

// ==========================================================
// Decrypt Message
// ==========================================================

export async function decryptMessage(
    ciphertext,
    encryptedKey,
    nonce,
    privateKey
) {

    const aesKeyRaw =
        await crypto.subtle.decrypt(
            {
                name: "RSA-OAEP",
            },
            privateKey,
            base64ToArrayBuffer(
                encryptedKey
            )
        );

    const aesKey =
        await crypto.subtle.importKey(
            "raw",
            aesKeyRaw,
            {
                name: "AES-GCM",
            },
            false,
            [
                "decrypt",
            ]
        );

    const plaintext =
        await crypto.subtle.decrypt(
            {
                name: "AES-GCM",
                iv: new Uint8Array(
                    base64ToArrayBuffer(
                        nonce
                    )
                ),
            },
            aesKey,
            base64ToArrayBuffer(
                ciphertext
            )
        );

    return new TextDecoder().decode(
        plaintext
    );

}