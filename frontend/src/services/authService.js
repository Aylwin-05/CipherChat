import api from "../api/api";

const authService = {

    // ======================================================
    // Send OTP
    // ======================================================

    async sendOTP(email) {

        const response = await api.post(
            "/auth/send-otp",
            {
                email,
            }
        );

        return response.data;

    },

    // ======================================================
    // Verify OTP
    // ======================================================

    async verifyOTP(email, otp) {

        const response = await api.post(
            "/auth/verify-otp",
            {
                email,
                otp,
            }
        );

        return response.data;

    },
    async refreshAccessToken() {

    const refreshToken =
        this.getRefreshToken();

    const response =
        await api.post(
            "/auth/refresh",
            {
                refresh_token:
                    refreshToken,
            }
        );

    localStorage.setItem(
        "access_token",
        response.data.access_token
    );

    return response.data.access_token;

    },

    // ======================================================
    // Get Logged-in User
    // ======================================================

    async getCurrentUser() {

        const response = await api.get(
            "/users/me"
        );

        return response.data;

    },

    // ======================================================
    // Token Helpers
    // ======================================================

    saveTokens(
        accessToken,
        refreshToken,
    ) {

        localStorage.setItem(
            "access_token",
            accessToken,
        );

        localStorage.setItem(
            "refresh_token",
            refreshToken,
        );

    },

    getAccessToken() {

        return localStorage.getItem(
            "access_token",
        );

    },

    getRefreshToken() {

        return localStorage.getItem(
            "refresh_token",
        );

    },

    // ======================================================
    // User Helpers
    // ======================================================

    saveUser(user) {

        localStorage.setItem(
            "user",
            JSON.stringify(user),
        );

    },

    getStoredUser() {

        const user =
            localStorage.getItem("user");

        return user
            ? JSON.parse(user)
            : null;

    },

    // ======================================================
    // Load Current User From Backend
    // ======================================================

    async loadCurrentUser() {

        const user =
            await this.getCurrentUser();

        this.saveUser(user);

        return user;

    },

    // ======================================================
    // Login Helper
    // ======================================================

    async login(
        accessToken,
        refreshToken,
    ) {

        this.saveTokens(
            accessToken,
            refreshToken,
        );

    },

    // ======================================================
    // Logout
    // ======================================================

    logout() {

        localStorage.removeItem(
            "access_token",
        );

        localStorage.removeItem(
            "refresh_token",
        );

        localStorage.removeItem(
            "user",
        );

    },

};

export default authService;