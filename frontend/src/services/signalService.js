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
import recoveryService from "./recoveryService";
import { signalKeyStore } from "../crypto/signal/keyStore";
import { replenishOneTimePrekeys } from "../crypto/signal/prekeyManager";
import { clearKeyPair } from "../crypto/keyStorage";
import { b64encode } from "../crypto/signal/bytes";
import {
    generateDeviceIdentity,
    generateOneTimePrekeys,
    generateDeviceId,
    buildRegisterPayload,
} from "../crypto/signal/identity";

// ==========================================================
// First-run device registration is NOT idempotent by itself:
// concurrent callers (login() + the AuthProvider boot effect,
// both doubled by React StrictMode) can each pass the "no meta
// yet" check and register a DIFFERENT device — leaving orphaned
// device rows on the server whose envelopes nothing decrypts.
//
// Guard with a shared in-flight promise (same-tab) and, when
// available, the Web Locks API (cross-tab). Every caller after
// the first awaits the SAME registration.
// ==========================================================

let registrationPromise = null;

function withDeviceLock(fn) {

    if (navigator?.locks?.request) {

        return navigator.locks.request(
            "cipherchat-device-register",
            fn,
        );

    }

    return fn();

}

export function ensureDeviceRegistered({
    platform = "web",
    deviceName = null,
    platformVersion = null,
    appVersion = null,
    email = null,
} = {}) {

    if (registrationPromise) {

        return registrationPromise;

    }

    registrationPromise = withDeviceLock(() =>

        (async () => {

            // Double-checked: the first caller may have completed
            // while we were waiting on the lock.
            const existing =
                await signalKeyStore.getMeta();

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

            // The account's recovery key was created by THIS
            // registration: unlock the sync secret right away and
            // surface the code so the UI can show it once.
            let recoveryCode = null;

            if (response.recovery_code) {

                try {

                    await recoveryService.unlockFromRegistration({
                        code: response.recovery_code,
                        salt: response.recovery_salt,
                        wrapped_key: response.recovery_wrapped_key,
                        email,
                    });

                    recoveryCode = response.recovery_code;

                }
                catch (error) {

                    console.error(
                        "Recovery auto-unlock failed:",
                        error
                    );

                }

            }

            return {
                deviceId,
                isPrimary,
                generated: true,
                recoveryCode,
            };

        })()

    );

    return registrationPromise.finally(() => {

        registrationPromise = null;

    });

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
//
// preserveSyncSecret: logout on the SAME browser keeps the
// account sync secret so the next login does not re-prompt
// for the recovery code — history stays unlocked locally.
// ==========================================================

export async function wipeDeviceData({
    removeFromServer = true,
    preserveSyncSecret = false,
} = {}) {

    const meta = await signalKeyStore.getMeta();

    const syncRecord = preserveSyncSecret
        ? await signalKeyStore.getSyncRecord()
        : null;

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

    // The account RSA key pair must not survive logout — it
    // decrypts history and must not linger in any script-readable
    // storage once the session is gone.
    await clearKeyPair();

    if (syncRecord?.secret) {

        await signalKeyStore.saveSyncSecret(
            syncRecord.secret,
            syncRecord.email,
        );

    }

}