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

                        encrypted_key:
                            encrypted.encrypted_key,

                        nonce:
                            encrypted.nonce,

                        message_type:
                            "text",

                        reply_to_id:
                            replyToId,

                    }

                );

            return response.data;

        }

};

export default messageService;