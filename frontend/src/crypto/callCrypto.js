// ==========================================================
// CipherChat Call E2EE (insertable streams)
//
// Voice/video media is encrypted frame-by-frame in the browser
// with AES-256-GCM via RTCRtpScriptTransform (WebRTC encoded
// transforms). The call key is NEVER sent over the wire: both
// peers derive it locally from the account sync secret (the
// 32-byte key that already exists only on the user's own
// devices and is used for cross-device history sync) plus the
// call ID. The server relays only opaque RTP ciphertext, so a
// compromised relay still cannot decrypt the conversation.
//
// Key schedule (caller/callee symmetric, no key exchange):
//   base   = HKDF(secret, ikm=callId, info="CipherChatCall", 64)
//   sendKey = base[0:32]   (derived with per-side label below)
//   recvKey = base[32:64]
// Direction labels make the streams independent per direction.
//
// Browsers without RTCRtpScriptTransform (Safari, older
// Firefox) fall back to unencrypted media so calls still work;
// the UI flags that the media leg is not protected.
// ==========================================================

import { signalKeyStore } from "./signal/keyStore";
import { hkdf } from "./signal/primitives";
import { utf8Encode, concatBytes } from "./signal/bytes";
import { b64decode } from "./signal/bytes";

const HKDF_INFO = utf8Encode("CipherChatCall");
const HKDF_INFO_SEND = utf8Encode("CipherChatCallSend");
const HKDF_INFO_RECV = utf8Encode("CipherChatCallRecv");

const AAD = utf8Encode("CipherChatCallFrame");

export function supportsFrameEncryption() {

    return (
        typeof window !== "undefined" &&
        typeof RTCRtpScriptTransform !== "undefined" &&
        typeof Worker !== "undefined" &&
        typeof TransformStream !== "undefined"
    );

}

async function deriveBaseSecret(callId) {

    const secretB64 = await signalKeyStore.getSyncSecret();

    if (!secretB64) {
        return null;
    }

    const secret = b64decode(secretB64);

    return hkdf(
        secret,
        utf8Encode(callId),
        HKDF_INFO,
        64,
    );

}

// Derive the per-direction send/recv keys for this call.
// isCaller distinguishes the offerer from the answerer so the
// two directions never share a key.
export async function deriveCallKeyPair(callId, isCaller) {

    const base = await deriveBaseSecret(callId);

    if (!base) {
        return null;
    }

    const sendInfo = isCaller
        ? HKDF_INFO_SEND
        : HKDF_INFO_RECV;

    const recvInfo = isCaller
        ? HKDF_INFO_RECV
        : HKDF_INFO_SEND;

    const sendKey = hkdf(
        new Uint8Array(0),
        base.slice(0, 32),
        concatBytes(HKDF_INFO, sendInfo),
        32,
    );

    const recvKey = hkdf(
        new Uint8Array(0),
        base.slice(32),
        concatBytes(HKDF_INFO, recvInfo),
        32,
    );

    return {
        sendKey,
        recvKey,
        isEncrypted: true,
    };

}

// The worker payload (cloned to the encoder worker).
export function buildWorkerOptions(operation, keyBytes) {

    return {
        operation,
        key: keyBytes,
        aad: AAD,
    };

}

export { AAD };