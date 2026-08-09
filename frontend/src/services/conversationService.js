import api from "../api/api";

const conversationService = {

    //==========================================================
    // Get All Conversations
    //==========================================================

    async getConversations() {

        try {

            const response = await api.get(
                "/conversations/"
            );

            return response.data;

        }

        catch (error) {

            console.error(
                "Failed to load conversations",
                error
            );

            throw error;

        }

    },

    //==========================================================
    // Create or Open Private Conversation
    //==========================================================

    async createPrivateConversation(
        userId,
    ) {

        try {

            const response = await api.post(

                "/conversations/private",

                {

                    user_id: userId,

                }

            );

            return response.data;

        }

        catch (error) {

            console.error(
                "Failed to create conversation",
                error
            );

            throw error;

        }

    },

    //==========================================================
    // Refresh Conversation List
    //==========================================================

    async refresh() {

        return await this.getConversations();

    },

};

export default conversationService;