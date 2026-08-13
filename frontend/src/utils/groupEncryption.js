import {
    arrayBufferToBase64,
} from "../crypto/base64";

import {
    generateFileKey,
    wrapFileKey,
} from "./fileEncryption";

import {
    decryptMessage,
} from "../crypto/cryptoService";

// ==========================================================
// GROUP CHAT ENCRYPTION
//
// A group message is encrypted with a FRESH AES-256-GCM key.
// That key is then wrapped (RSA-OAEP) to EVERY member's public
// key, including the sender's own, so any member's device can
// unwrap it and decrypt. The server stores ciphertext + the
// wrapped copies only — never plaintext, never the raw key.
// ==========================================================

// ==========================================================
// Encrypt a group message for a set of members
//
// members: [{ user_id, public_key }, ...]
// Returns the backend payload: ciphertext, nonce and the
// per-recipient wrapped key list.
// ==========================================================

export async function encryptGroupMessage(
    plaintext,
    members,
) {

    const key =
        await generateFileKey();

    const iv =
        crypto.getRandomValues(
            new Uint8Array(12)
        );

    const encoder =
        new TextEncoder();

    const encryptedMessage =
        await crypto.subtle.encrypt(
            {
                name: "AES-GCM",
                iv,
            },
            key,
            encoder.encode(
                plaintext
            )
        );

    const rawKey =
        await crypto.subtle.exportKey(
            "raw",
            key,
        );

    const recipientKeys = [];

    for (const member of members) {

        if (!member?.public_key) continue;

        recipientKeys.push({

            user_id:
                member.user_id,

            encrypted_key:
                await wrapFileKey(
                    rawKey,
                    member.public_key,
                ),

        });

    }

    return {

        ciphertext:
            arrayBufferToBase64(
                encryptedMessage
            ),

        encrypted_key_sender:
            "signal",

        encrypted_key_receiver:
            "signal",

        nonce:
            arrayBufferToBase64(
                iv.buffer
            ),

        message_type:
            "text",

        recipient_keys:
            recipientKeys,

    };

}

// ==========================================================
// Decrypt a group message with the local RSA private key
//
// Finds the wrapped key copy addressed to the current user
// and unwraps it with the local private key.
// ==========================================================

export async function decryptGroupMessage(
    message,
    privateKeyBase64,
    currentUserId,
) {

    const ownKey = (
        message.recipient_keys ?? []
    ).find(
        key =>
            String(key.user_id) ===
            String(currentUserId)
    );

    if (!ownKey) {

        throw new Error(
            "No key copy for this user."
        );

    }

    return await decryptMessage(
        message.ciphertext,
        ownKey.encrypted_key,
        message.nonce,
        privateKeyBase64,
    );

}