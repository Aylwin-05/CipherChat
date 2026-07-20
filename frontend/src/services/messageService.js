import api from "../api/api";

const messageService = {
    async getMessages(conversationId) {
        const response = await api.get(
            `/messages/${conversationId}`
        );

        return response.data;
    },

    async sendMessage(
        conversationId,
        content,
    ) {
        const response = await api.post(
            "/messages/send",
            {
                conversation_id: conversationId,
                content,
            },
        );

        return response.data;
    },
};

export default messageService;