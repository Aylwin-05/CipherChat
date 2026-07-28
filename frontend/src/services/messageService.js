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
                        encrypted.encrypted_key_sender,

                    encrypted_key_receiver:
                        encrypted.encrypted_key_receiver,

                    nonce:
                        encrypted.nonce,

                    message_type:
                        "text",

                    reply_to_id:
                        replyToId,

                }

            );

        return response.data;

    },

    // ======================================================
    // Upload Attachment
    // ======================================================

    async uploadAttachment(
        messageId,
        file,
    ) {

        const formData = new FormData();

        formData.append(
            "file",
            file
        );

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