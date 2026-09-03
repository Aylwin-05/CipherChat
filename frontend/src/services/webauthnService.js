import api from "../api/api";

function bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary)
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");
}

function base64urlToBuffer(base64url) {
    let base64 = base64url
        .replace(/-/g, "+")
        .replace(/_/g, "/");
    while (base64.length % 4) {
        base64 += "=";
    }
    const binary = atob(base64);
    const buffer = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        buffer[i] = binary.charCodeAt(i);
    }
    return buffer.buffer;
}

const webauthnService = {

    async registerBegin(deviceName) {
        const response = await api.post(
            "/webauthn/register/begin",
            { device_name: deviceName || null },
        );
        return response.data;
    },

    async registerComplete(credentialId, clientDataJson, attestationObject, deviceName) {
        const response = await api.post(
            "/webauthn/register/complete",
            {
                credential_id: credentialId,
                client_data_json: clientDataJson,
                attestation_object: attestationObject,
                device_name: deviceName || null,
            },
        );
        return response.data;
    },

    async loginBegin(email) {
        const response = await api.post(
            "/webauthn/login/begin",
            { email },
        );
        return response.data;
    },

    async loginComplete(credentialId, clientDataJson, authenticatorData, signature, userHandle) {
        const response = await api.post(
            "/webauthn/login/complete",
            {
                credential_id: credentialId,
                client_data_json: clientDataJson,
                authenticator_data: authenticatorData,
                signature: signature,
                user_handle: userHandle || null,
            },
        );
        return response.data;
    },

    async listCredentials() {
        const response = await api.get(
            "/webauthn/credentials",
        );
        return response.data;
    },

    async deleteCredential(credentialId) {
        const response = await api.delete(
            `/webauthn/credentials/${credentialId}`,
        );
        return response.data;
    },

    async createPasskey(deviceName) {
        const options = await this.registerBegin(deviceName);

        const publicKeyOptions = {
            challenge: base64urlToBuffer(options.challenge),
            rp: options.rp,
            user: {
                id: base64urlToBuffer(options.user.id),
                name: options.user.name,
                displayName: options.user.displayName,
            },
            pubKeyCredParams: options.pubKeyCredParams,
            timeout: options.timeout,
            attestation: options.attestation,
            authenticatorSelection: options.authenticatorSelection,
        };

        const credential = await navigator.credentials.create({
            publicKey: publicKeyOptions,
        });

        const result = await this.registerComplete(
            bufferToBase64url(credential.rawId),
            bufferToBase64url(
                credential.response.clientDataJSON
            ),
            bufferToBase64url(
                credential.response.attestationObject
            ),
            deviceName,
        );

        return result;
    },

    async authenticateWithPasskey(email) {
        const options = await this.loginBegin(email);

        const publicKeyOptions = {
            challenge: base64urlToBuffer(options.challenge),
            rpId: options.rpId,
            timeout: options.timeout,
            userVerification: options.userVerification,
            allowCredentials: options.allowCredentials.map(
                (cred) => ({
                    ...cred,
                    id: base64urlToBuffer(cred.id),
                })
            ),
        };

        const assertion = await navigator.credentials.get({
            publicKey: publicKeyOptions,
        });

        const result = await this.loginComplete(
            bufferToBase64url(assertion.rawId),
            bufferToBase64url(
                assertion.response.clientDataJSON
            ),
            bufferToBase64url(
                assertion.response.authenticatorData
            ),
            bufferToBase64url(assertion.response.signature),
            assertion.response.userHandle
                ? bufferToBase64url(
                      assertion.response.userHandle
                  )
                : null,
        );

        return result;
    },
};

export default webauthnService;
