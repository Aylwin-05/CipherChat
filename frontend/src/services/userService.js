import api from "../api/api";

const userService = {
    // ======================================================
    // Get Current User
    // ======================================================

    async getCurrentUser() {
        const response = await api.get("/users/me");
        return response.data;
    },
};

export default userService;