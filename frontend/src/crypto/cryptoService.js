// ==========================================================
// CipherChat Crypto Service
//
// Hybrid Encryption
//
// RSA-OAEP 2048
// AES-256-GCM
//
// Browser generates and stores identity keys.
// Backend stores ONLY the public key.
// ==========================================================

import {
    arrayBufferToBase64,
    base64ToArrayBuffer,
} from "./base64";

// ==========================================================
// RSA KEY GENERATION
// ==========================================================

export async function generateIdentityKeys() {

    const keyPair =
        await crypto.subtle.generateKey(
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

    const publicKey =
        await exportPublicKey(
            keyPair.publicKey
        );

    const privateKey =
        await exportPrivateKey(
            keyPair.privateKey
        );

    return {

        publicKey,

        privateKey,

    };

}

// ==========================================================
// EXPORT PUBLIC KEY
// ==========================================================

export async function exportPublicKey(
    key
) {

    const exported =
        await crypto.subtle.exportKey(
            "spki",
            key
        );

    return arrayBufferToBase64(
        exported
    );

}

// ==========================================================
// EXPORT PRIVATE KEY
// ==========================================================

export async function exportPrivateKey(
    key
) {

    const exported =
        await crypto.subtle.exportKey(
            "pkcs8",
            key
        );

    return arrayBufferToBase64(
        exported
    );

}

// ==========================================================
// IMPORT PUBLIC KEY
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
// IMPORT PRIVATE KEY
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
// AES-256 KEY
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
// EXPORT RAW AES KEY
// ==========================================================

async function exportAESKey(
    aesKey
) {

    return await crypto.subtle.exportKey(
        "raw",
        aesKey
    );

}

// ==========================================================
// IMPORT RAW AES KEY
// ==========================================================

async function importAESKey(
    rawKey
) {

    return await crypto.subtle.importKey(
        "raw",
        rawKey,
        {
            name: "AES-GCM",
        },
        false,
        [
            "decrypt",
        ]
    );

}
// ==========================================================
// ENCRYPT MESSAGE
// ==========================================================

export async function 
encryptMessage(
    plaintext,
    senderPublicKey,
    receiverPublicKey
) 
{

    // ----------------------------------------------
    // Generate one-time AES key
    // ----------------------------------------------

    const aesKey =
        await generateAESKey();

    // ----------------------------------------------
    // Random IV (Nonce)
    // ----------------------------------------------

    const iv =
        crypto.getRandomValues(
            new Uint8Array(12)
        );

    // ----------------------------------------------
    // Encrypt plaintext with AES-GCM
    // ----------------------------------------------

    const encoder =
        new TextEncoder();

    const encryptedMessage =
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

    // ----------------------------------------------
    // Export AES key
    // ----------------------------------------------

    const rawAESKey =
        await exportAESKey(
            aesKey
        );

    // ----------------------------------------------
    // Encrypt AES key using RSA
    // ----------------------------------------------

    const senderKey =
        await importPublicKey(senderPublicKey);

    const receiverKey =
        await importPublicKey(receiverPublicKey);

    const encryptedSenderKey =
        await crypto.subtle.encrypt(
            {
                name:"RSA-OAEP"
            },
            senderKey,
            rawAESKey
        );

    const encryptedReceiverKey =
        await crypto.subtle.encrypt(
            {
                name:"RSA-OAEP"
            },
            receiverKey,
            rawAESKey
        );

    // ----------------------------------------------
    // Return backend payload
    // ----------------------------------------------

    return {

        ciphertext:
            arrayBufferToBase64(
                encryptedMessage
            ),

        encrypted_key_sender:
            arrayBufferToBase64(
                encryptedSenderKey
            ),

        encrypted_key_receiver:
            arrayBufferToBase64(
                encryptedReceiverKey
            ),

        nonce:
            arrayBufferToBase64(
                iv.buffer
            ),

        message_type:"text"

    };

}

// ==========================================================
// ENCRYPT BINARY DATA
// ==========================================================

export async function encryptBytes(
    bytes,
    recipientPublicKeyBase64,
) {

    const recipientPublicKey =
        await importPublicKey(
            recipientPublicKeyBase64
        );

    const aesKey =
        await generateAESKey();

    const iv =
        crypto.getRandomValues(
            new Uint8Array(12)
        );

    const encryptedBytes =
        await crypto.subtle.encrypt(
            {
                name: "AES-GCM",
                iv,
            },
            aesKey,
            bytes
        );

    const rawAESKey =
        await exportAESKey(
            aesKey
        );

    const encryptedAESKey =
        await crypto.subtle.encrypt(
            {
                name: "RSA-OAEP",
            },
            recipientPublicKey,
            rawAESKey
        );

    return {

        ciphertext:
            arrayBufferToBase64(
                encryptedBytes
            ),

        encrypted_key:
            arrayBufferToBase64(
                encryptedAESKey
            ),

        nonce:
            arrayBufferToBase64(
                iv.buffer
            ),

    };

}
// ==========================================================
// DECRYPT MESSAGE
// ==========================================================

export async function decryptMessage(
    ciphertextBase64,
    encryptedKeyBase64,
    nonceBase64,
    privateKeyBase64,
) {

    // ----------------------------------------------
    // Import private RSA key
    // ----------------------------------------------

    const privateKey =
        await importPrivateKey(
            privateKeyBase64
        );

    // ----------------------------------------------
    // Decrypt AES key
    // ----------------------------------------------

    const rawAESKey =
        await crypto.subtle.decrypt(
            {
                name: "RSA-OAEP",
            },
            privateKey,
            base64ToArrayBuffer(
                encryptedKeyBase64
            )
        );

    // ----------------------------------------------
    // Import AES key
    // ----------------------------------------------

    const aesKey =
        await importAESKey(
            rawAESKey
        );

    // ----------------------------------------------
    // Decrypt ciphertext
    // ----------------------------------------------

    const plaintext =
        await crypto.subtle.decrypt(
            {
                name: "AES-GCM",
                iv: new Uint8Array(
                    base64ToArrayBuffer(
                        nonceBase64
                    )
                ),
            },
            aesKey,
            base64ToArrayBuffer(
                ciphertextBase64
            )
        );

    return new TextDecoder().decode(
        plaintext
    );

}

// ==========================================================
// DECRYPT BINARY DATA
// ==========================================================

export async function decryptBytes(
    ciphertextBase64,
    encryptedKeyBase64,
    nonceBase64,
    privateKeyBase64,
) {

    const privateKey =
        await importPrivateKey(
            privateKeyBase64
        );

    const rawAESKey =
        await crypto.subtle.decrypt(
            {
                name: "RSA-OAEP",
            },
            privateKey,
            base64ToArrayBuffer(
                encryptedKeyBase64
            )
        );

    const aesKey =
        await importAESKey(
            rawAESKey
        );

    return await crypto.subtle.decrypt(
        {
            name: "AES-GCM",
            iv: new Uint8Array(
                base64ToArrayBuffer(
                    nonceBase64
                )
            ),
        },
        aesKey,
        base64ToArrayBuffer(
            ciphertextBase64
        )
    );

}

// ==========================================================
// VALIDATION
// ==========================================================

    export function isEncryptedMessage(
        message
    ) {

        return !!(

            message &&

            message.ciphertext &&

            (
                message.encrypted_key_sender ||
                message.encrypted_key_receiver
            ) &&

            message.nonce

        );

    }

// ==========================================================
// SAFE DECRYPT
// ==========================================================
export async function safeDecrypt(
    message,
    privateKey,
    currentUserId,
) {

    try {

        if (!isEncryptedMessage(message)) {

            return message;

        }

        const encryptedKey =
            message.sender_id === currentUserId
                ? message.encrypted_key_sender
                : message.encrypted_key_receiver;

        const plaintext =
            await decryptMessage(
                message.ciphertext,
                encryptedKey,
                message.nonce,
                privateKey,
            );

        return {

            ...message,

            content: plaintext,

        };

    }

    catch (error) {

        console.error(
            "Failed to decrypt message:",
            error
        );

        return {

            ...message,

            content:
                "[Unable to decrypt]",

        };

    }

}