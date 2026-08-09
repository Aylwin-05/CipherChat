import api from "../api/api";
import { getPrivateKey } from "../crypto/keyStorage";
import { base64ToArrayBuffer } from "../crypto/base64";
import {
    decryptFile,
    unwrapFileKey,
} from "../utils/fileEncryption";

const attachmentService = {

    async upload(messageId, file) {

        const formData = new FormData();

        formData.append("file", file);

        const response = await api.post(

            `/attachments/upload/${messageId}`,

            formData,

            {
                headers: {
                    "Content-Type": "multipart/form-data",
                },
            }

        );

        return response.data;

    },

    downloadUrl(id) {

        const base =
            import.meta.env.VITE_API_URL || "/api/v1";

        return `${base}/attachments/${id}`;

    },

    // ==========================================================
    // Get Attachment (decrypted when the file key is provided)
    //
    // `wrappedKey` is the RSA-OAEP ciphertext of the file's AES
    // key (base64). It is unwrapped with the local private key,
    // then the stored ciphertext blob is AES-GCM decrypted so
    // the browser gets the original plaintext file.
    // ==========================================================

    async getAttachment(
        id,
        {
            wrappedKey = null,
            nonce = null,
        } = {},
    ) {

        const response = await api.get(

            `/attachments/${id}`,

            {
                responseType: "blob",
            }

        );

        let blob = response.data;

        if (wrappedKey && nonce) {

            try {

                const rawKey =
                    await unwrapFileKey(
                        wrappedKey,
                        getPrivateKey()
                    );

                blob =
                    await decryptFile(
                        blob,
                        rawKey,
                        base64ToArrayBuffer(nonce)
                    );

            }

            catch (error) {

                console.error(
                    "Attachment decryption failed:",
                    error
                );

                throw error;

            }

        }

        return URL.createObjectURL(blob);

    },

};

export default attachmentService;