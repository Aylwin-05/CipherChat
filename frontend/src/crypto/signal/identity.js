// ==========================================================
// CipherChat Signal Identity & Registration Payload
//
// Generates the long-term device identity (Ed25519), the
// signed prekey (X25519) and a batch of one-time prekeys,
// then builds the payload for POST /devices/register in a
// shape identical to the backend's RegisterDeviceRequest.
// ==========================================================

import {
    generateEd25519Keypair,
    generateX25519Keypair,
    ed25519Sign,
} from "./primitives.js";
import {
    deriveX25519FromEd25519,
    getX25519IdentityPublic,
} from "./x3dh.js";
import { x25519 } from "./primitives.js";
import { b64encode, b64decode } from "./bytes.js";

// Number of one-time prekeys uploaded at registration
export const OPK_BATCH_SIZE = 100;

// ==========================================================
// Generate complete device identity material
// ==========================================================

export function generateDeviceIdentity({ signedPrekeyId = 1 } = {}) {
    const identity = generateEd25519Keypair();          // { privateKey, publicKey }
    const x25519IdentityPublic = getX25519IdentityPublic(identity.privateKey);

    const signedPrekey = generateX25519Keypair();       // { privateKey, publicKey }
    const signature = ed25519Sign(identity.privateKey, signedPrekey.publicKey);

    return {
        deviceId: null, // assigned by the caller
        identity: {
            privateKey: identity.privateKey,
            publicKey: identity.publicKey,
            x25519Public: x25519IdentityPublic,
        },
        signedPrekey: {
            keyId: signedPrekeyId,
            publicKey: signedPrekey.publicKey,
            signature,
            privateKey: signedPrekey.privateKey,
        },
    };
}

// ==========================================================
// Generate one-time prekeys (public + private)
// ==========================================================

export function generateOneTimePrekeys({ startId = 1, count = OPK_BATCH_SIZE } = {}) {
    const opks = [];
    for (let i = 0; i < count; i++) {
        const keyPair = generateX25519Keypair();
        opks.push({
            keyId: startId + i,
            publicKey: keyPair.publicKey,
            privateKey: keyPair.privateKey,
        });
    }
    return opks;
}

// ==========================================================
// Client-side "encryption" of private key material
//
// The backend stores private keys as opaque base64 blobs
// (its tests use b64(b64(raw)) as the placeholder convention).
// The real key stays in the local IndexedDB key store; this
// value is only what the server keeps on record.
// ==========================================================

export function wrapPrivateKey(rawBytes) {
    return b64encode(utf8Encode(b64encode(rawBytes)));
}

function utf8Encode(text) {
    return new TextEncoder().encode(text);
}

// ==========================================================
// Build the /devices/register payload
// ==========================================================

export function buildRegisterPayload({
    deviceId,
    platform = "web",
    deviceName = null,
    platformVersion = null,
    appVersion = null,
    identity,              // from generateDeviceIdentity()
    signedPrekey,          // from generateDeviceIdentity()
    oneTimePrekeys,        // from generateOneTimePrekeys()
}) {
    return {
        device_id: deviceId,
        platform,
        device_name: deviceName,
        platform_version: platformVersion,
        app_version: appVersion,
        identity_key_public: b64encode(identity.publicKey),
        identity_key_x25519: b64encode(identity.x25519Public),
        identity_key_private_encrypted: wrapPrivateKey(identity.privateKey),
        signed_prekey_public: b64encode(signedPrekey.publicKey),
        signed_prekey_private_encrypted: wrapPrivateKey(signedPrekey.privateKey),
        signed_prekey_id: signedPrekey.keyId,
        signed_prekey_signature: b64encode(signedPrekey.signature),
        one_time_prekeys: oneTimePrekeys.map((opk) => ({
            key_id: opk.keyId,
            public_key: b64encode(opk.publicKey),
            private_key_encrypted: wrapPrivateKey(opk.privateKey),
        })),
    };
}

// ==========================================================
// Device ID generation
// ==========================================================

export function generateDeviceId() {
    return `web-${crypto.randomUUID()}`;
}

export { b64encode, b64decode };