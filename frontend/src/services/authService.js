import api, {
    refreshAccessToken,
    setAccessToken,
    clearAccessToken,
} from "../api/api";

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

    // ======================================================
    // Refresh Access Token
    //
    // The refresh token lives in the HttpOnly cookie, which the
    // browser attaches automatically. Nothing is read from
    // localStorage and nothing is written back to it.
    // ======================================================

    async refreshAccessToken() {

        const token =
            await refreshAccessToken();

        return token;

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
    // Token Helpers (memory only)
    // ======================================================

    login(accessToken) {

        setAccessToken(accessToken);

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
    // Logout
    //
    // Revokes the refresh-token family server-side (the cookie
    // travels along automatically) and clears local state.
    // ======================================================

    async logout() {

        try {

            await api.post(
                "/auth/logout",
                {},
            );

        }

        catch (error) {

            console.error(
                "Logout revocation failed:",
                error
            );

        }

        clearAccessToken();

        localStorage.removeItem(
            "user",
        );

    },

};

export default authService;