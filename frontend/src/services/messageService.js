import api from "../api/api";

const messageService = {

    // ======================================================
    // Get Messages
    // ======================================================

    async getMessages(
        conversationId,
    ) {

        const response =
            await api.get(
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
    ) {

        const response =
            await api.post(

                "/messages/send",

                {

                    conversation_id:
                        conversationId,

                    ciphertext:
                        encrypted.ciphertext,

                    encrypted_key:
                        encrypted.encrypted_key,

                    nonce:
                        encrypted.nonce,

                    message_type:
                        "text",

                }

            );

        return response.data;

    },

};

export default messageService;