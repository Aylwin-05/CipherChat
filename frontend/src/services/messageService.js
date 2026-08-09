import api from "../api/api";

const messageService = {

    // ======================================================
    // Get Messages
    // ======================================================

    async getMessages(conversationId) {

        const response = await api.get(
            `/messages/${conversationId}`
        );

        return response.data;

    },

    // ======================================================
    // Send Encrypted Message
    //
    // Signal mode: ciphertext carries the envelope JSON;
    // legacy RSA fields receive placeholders so the backend
    // schema stays untouched.
    // ======================================================

    async sendMessage(
        conversationId,
        encrypted,
        replyToId = null,
    ) {

        const response =
            await api.post(

                "/messages/send",

                {

                    conversation_id:
                        conversationId,

                    ciphertext:
                        encrypted.ciphertext,

                    encrypted_key_sender:
                        encrypted.encrypted_key_sender ||
                        "signal",

                    encrypted_key_receiver:
                        encrypted.encrypted_key_receiver ||
                        "signal",

                    nonce:
                        encrypted.nonce ||
                        "signal",

                    message_type:
                        "text",

                    reply_to_id:
                        replyToId,

                }

            );

        return response.data;

    },

    // ======================================================
    // Delete For Everyone (sender only)
    // ======================================================

    async deleteForEveryone(messageId) {

        const response =
            await api.delete(
                `/messages/${messageId}`
            );

        return response.data;

    },

    // ======================================================
    // Delete For Me (any participant)
    // ======================================================

    async deleteForMe(messageId) {

        const response =
            await api.delete(
                `/messages/${messageId}/me`
            );

        return response.data;

    },

    // ======================================================
    // Upload Attachment
    //
    // Client-side encrypted: the file is AES-GCM encrypted in
    // the browser; the file's AES key is RSA-OAEP wrapped for
    // the sender and the recipient, and the wrap + IV are sent
    // as form fields so the backend stores them alongside the
    // ciphertext (the backend never sees plaintext or the key).
    // ======================================================

    async uploadAttachment(
        messageId,
        file,
        encryption = null,
    ) {

        const formData = new FormData();

        formData.append(
            "file",
            file
        );

        if (encryption) {

            formData.append(
                "encrypted",
                "true"
            );

            formData.append(
                "encrypted_key_sender",
                encryption.encrypted_key_sender
            );

            formData.append(
                "encrypted_key_receiver",
                encryption.encrypted_key_receiver
            );

            formData.append(
                "nonce",
                encryption.nonce
            );

        }

        const response =
            await api.post(

                `/attachments/upload/${messageId}`,

                formData,

                {
                    headers: {
                        "Content-Type":
                            "multipart/form-data",
                    },
                }

            );

        return response.data;

    },

};

export default messageService;