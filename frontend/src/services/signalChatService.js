// ==========================================================
// CipherChat Signal Chat Service
//
// High-level wrapper used by the chat UI:
//   - encrypt():  fetch peer bundle (once), run X3DH first
//                 message or use the established ratchet session
//   - decrypt():  parse an incoming envelope JSON and decrypt
//                 via the local device's session
//
// Envelope JSON is carried in the message "ciphertext" field of
// the existing REST/WS message schema (legacy RSA fields get
// placeholder values), keeping the backend API unchanged.
// ==========================================================

import { signalKeyStore } from "../crypto/signal/keyStore.js";
import { IndexedDbSessionStore } from "../crypto/signal/sessionStore.js";
import { SignalSessionManager } from "../crypto/signal/session.js";
import { SignalEnvelope } from "../crypto/signal/message.js";
import { b64decode } from "../crypto/signal/bytes.js";

export class SignalChatError extends Error {}

const PEER_MAP_ID = "peer-map";

// ==========================================================
// Session manager bound to the local device
// ==========================================================

export async function getSignalSessionManager(keyStore = signalKeyStore) {
    const identity = await keyStore.getIdentity();
    if (!identity) {
        throw new SignalChatError(
            "No Signal identity registered; re-login first.",
        );
    }
    return {
        manager: new SignalSessionManager(new IndexedDbSessionStore(keyStore)),
        identity,
        keyStore,
    };
}

// ==========================================================
// Local device
// ==========================================================

async function localDevice(keyStore) {
    const meta = await keyStore.getMeta();
    if (!meta?.deviceId) {
        throw new SignalChatError("Signal device not registered.");
    }
    return meta;
}

// ==========================================================
// Resolve which remote device a conversation maps to
// (first message picks devices[0]; afterwards it is pinned)
// ==========================================================

async function resolveRemoteDevice(
    keyStore,
    conversationId,
    remoteDevices,
) {
    const peers = (await keyStore.peekMeta(PEER_MAP_ID)) ?? {
        conversations: {},
    };

    let remoteDeviceId = peers.conversations[conversationId];
    if (remoteDeviceId) return remoteDeviceId;

    if (!remoteDevices?.length) {
        throw new SignalChatError("Peer has no registered devices.");
    }
    remoteDeviceId = remoteDevices[0].device_id;

    peers.conversations[conversationId] = remoteDeviceId;
    await keyStore.saveMeta({ id: PEER_MAP_ID, ...peers });
    return remoteDeviceId;
}

// ==========================================================
// Encrypt a plaintext for a conversation
//
// Pass remoteDevices (list from deviceService.getBundle) or a
// bundleProvider() that returns it; the first device is pinned
// for the conversation.
// ==========================================================

export async function encryptForConversation({
    conversationId,
    otherUserId = null,
    plaintext,
    remoteDevices = null,
    bundleProvider = null,
    keyStore = signalKeyStore,
}) {
    const { manager, identity } = await getSignalSessionManager(keyStore);
    const our = await localDevice(keyStore);

    if (!remoteDevices && bundleProvider) {
        remoteDevices = await bundleProvider();
    }

    const remoteDeviceId = await resolveRemoteDevice(
        keyStore,
        conversationId,
        remoteDevices,
    );

    const session = await manager.store.get(
        our.deviceId,
        remoteDeviceId,
        conversationId,
    );

    let envelope;
    if (session) {
        envelope = await manager.encrypt({
            ourDeviceId: our.deviceId,
            ourUserId: our.deviceId,
            remoteDeviceId,
            conversationId,
            plaintext: utf8Bytes(plaintext),
        });
    } else {
        const device = remoteDevices?.find(
            (d) => d.device_id === remoteDeviceId,
        );
        if (!device) {
            throw new SignalChatError("Peer device bundle unavailable.");
        }
        envelope = await manager.encryptFirst({
            ourDeviceId: our.deviceId,
            ourUserId: our.deviceId,
            ourIdentityPrivate: b64decode(identity.identityKeyPrivate),
            theirDeviceId: remoteDeviceId,
            theirBundle: device,
            conversationId,
            plaintext: utf8Bytes(plaintext),
        });
    }

    return {
        ciphertext: envelope.toJson(),
        type: envelope.type,
        deviceId: envelope.deviceId,
    };
}

// ==========================================================
// Decrypt an incoming message envelope
// ==========================================================

export async function decryptMessage({
    conversationId,
    ciphertext,
    keyStore = signalKeyStore,
}) {
    let envelope;
    try {
        envelope = SignalEnvelope.fromJson(ciphertext);
    } catch {
        throw new SignalChatError("Not a Signal envelope.");
    }

    if (envelope.type === "data") {
        return decryptData({ conversationId, envelope, keyStore });
    }
    if (envelope.type === "prekey") {
        return decryptPrekey({ conversationId, envelope, keyStore });
    }
    throw new SignalChatError(`Unknown envelope type: ${envelope.type}`);
}

async function decryptData({ conversationId, envelope, keyStore }) {
    const { manager } = await getSignalSessionManager(keyStore);
    const our = await localDevice(keyStore);
    const result = await manager.decrypt({
        envelope,
        ourDeviceId: our.deviceId,
        conversationId,
    });
    return utf8DecodeBytes(result.plaintext);
}

async function decryptPrekey({ conversationId, envelope, keyStore }) {
    const { manager, identity } = await getSignalSessionManager(keyStore);
    const our = await localDevice(keyStore);

    const spkId = envelope.x3dhInfo?.signed_prekey_id ?? null;
    const spk = spkId != null ? await keyStore.getSignedPrekey(spkId) : null;
    if (!spk) {
        throw new SignalChatError("Signed prekey not found for handshake.");
    }

    let oneTime = null;
    const opkId = envelope.x3dhInfo?.one_time_prekey_id ?? null;
    if (opkId != null) {
        oneTime = await keyStore.getOneTimePrekey(opkId);
        if (!oneTime) {
            throw new SignalChatError("One-time prekey not found.");
        }
    }

    const result = await manager.decryptFirst({
        envelope,
        ourDeviceId: our.deviceId,
        ourIdentityKey: b64decode(identity.identityKeyPrivate),
        signedPrekey: { key_id: spk.keyId, private_key: spk.privateKey },
        oneTimePrekey: oneTime
            ? { key_id: oneTime.keyId, private_key: oneTime.privateKey }
            : null,
        conversationId,
    });

    // One-time prekeys are single-use: purge locally
    if (oneTime) {
        await keyStore.removeOneTimePrekey(opkId);
    }

    return utf8DecodeBytes(result.plaintext);
}

// ==========================================================
// Helpers
// ==========================================================

function utf8Bytes(text) {
    return new TextEncoder().encode(text);
}

function utf8DecodeBytes(bytes) {
    return new TextDecoder().decode(bytes);
}