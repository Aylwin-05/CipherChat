// ==========================================================
// CipherChat Signal Device Service (frontend)
//
// Orchestrates first-run device registration:
//   1. generate Ed25519 identity + signed prekey + OPK batch
//   2. persist private material in the local IndexedDB store
//   3. POST /devices/register with the public payload
//   4. remember the device id / primary flag in the key store
// ==========================================================

import deviceService from "./deviceService";
import { signalKeyStore } from "../crypto/signal/keyStore";
import { replenishOneTimePrekeys } from "../crypto/signal/prekeyManager";
import { b64encode } from "../crypto/signal/bytes";
import {
    generateDeviceIdentity,
    generateOneTimePrekeys,
    generateDeviceId,
    buildRegisterPayload,
} from "../crypto/signal/identity";

export async function ensureDeviceRegistered({
    platform = "web",
    deviceName = null,
    platformVersion = null,
    appVersion = null,
} = {}) {
    const existing = await signalKeyStore.getMeta();
    if (existing?.deviceId) {
        return {
            deviceId: existing.deviceId,
            isPrimary: existing.isPrimary,
            generated: false,
        };
    }

    const deviceId = generateDeviceId();

    const { identity, signedPrekey } = generateDeviceIdentity();
    const oneTimePrekeys = generateOneTimePrekeys();

    // Persist private material locally BEFORE uploading anything
    await signalKeyStore.saveIdentity({
        deviceId,
        identityKeyPrivate: b64encode(identity.privateKey),
        identityKeyPublic: b64encode(identity.publicKey),
        x25519IdentityKeyPublic: b64encode(identity.x25519Public),
    });
    await signalKeyStore.saveSignedPrekey({
        keyId: signedPrekey.keyId,
        publicKey: b64encode(signedPrekey.publicKey),
        signature: b64encode(signedPrekey.signature),
        privateKey: b64encode(signedPrekey.privateKey),
    });
    await signalKeyStore.saveOneTimePrekeys(
        oneTimePrekeys.map((opk) => ({
            keyId: opk.keyId,
            publicKey: b64encode(opk.publicKey),
            privateKey: b64encode(opk.privateKey),
        })),
    );

    const payload = buildRegisterPayload({
        deviceId,
        platform,
        deviceName,
        platformVersion,
        appVersion,
        identity,
        signedPrekey,
        oneTimePrekeys,
    });

    const response = await deviceService.registerDevice(payload);
    const isPrimary = !!response.is_primary;

    await signalKeyStore.saveMeta({
        deviceId,
        isPrimary,
        platform,
        deviceName,
    });

    return { deviceId, isPrimary, generated: true };
}

// ==========================================================
// Current registered device
// ==========================================================

export async function getRegisteredDevice() {
    return signalKeyStore.getMeta();
}

// ==========================================================
// Replenish local one-time prekey pool (and mirror to server)
// ==========================================================

export async function replenishPreKeys(options = {}) {

    const meta = await signalKeyStore.getMeta();

    if (!meta?.deviceId) {

        return {

            replenished: 0,

            count: 0,

            uploaded: 0,

        };

    }

    return replenishOneTimePrekeys({

        keyStore: signalKeyStore,

        upload: (payload) => deviceService.uploadPreKeys({

            device_id: meta.deviceId,

            one_time_prekeys: payload,

        }),

        ...options,

    });

}

// ==========================================================
// Wipe the local device (logout / unlink)
//
// Best effort: remove the device from the server first (the
// primary device cannot be removed server-side), then always
// wipe every trace of key material from this browser.
// ==========================================================

export async function wipeDeviceData({ removeFromServer = true } = {}) {

    const meta = await signalKeyStore.getMeta();

    if (removeFromServer && meta?.deviceId) {

        try {

            await deviceService.removeDevice(meta.deviceId);

        }

        catch {

            // Primary device cannot be removed; wiping locally
            // still decrypts nothing after this point.

        }

    }

    await signalKeyStore.clearAll();

}