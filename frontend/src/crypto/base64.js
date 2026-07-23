// ==========================================================
// CipherChat Base64 Utilities
//
// Converts:
// ArrayBuffer <-> Base64 string
//
// Required because:
// Web Crypto API uses ArrayBuffer
// Backend API uses Base64 strings
// ==========================================================


// ==========================================================
// ArrayBuffer -> Base64
// ==========================================================

export function arrayBufferToBase64(
    buffer
) {

    const bytes =
        new Uint8Array(buffer);

    let binary = "";

    bytes.forEach(
        (byte) => {
            binary += String.fromCharCode(
                byte
            );
        }
    );

    return window.btoa(
        binary
    );

}


// ==========================================================
// Base64 -> ArrayBuffer
// ==========================================================

export function base64ToArrayBuffer(
    base64
) {

    const binary =
        window.atob(
            base64
        );

    const bytes =
        new Uint8Array(
            binary.length
        );


    for (
        let i = 0;
        i < binary.length;
        i++
    ) {

        bytes[i] =
            binary.charCodeAt(i);

    }


    return bytes.buffer;

}