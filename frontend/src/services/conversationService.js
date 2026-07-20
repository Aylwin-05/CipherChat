import api from "../api/api";

const conversationService = {
    async getConversations() {
        const response = await api.get(
            "/conversations"
        );

        return response.data;
    },
};

export default conversationService;