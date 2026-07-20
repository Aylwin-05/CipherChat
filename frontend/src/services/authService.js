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

    async verifyOTP(
        email,
        otp
    ) {
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
    // Logout
    // ======================================================

    logout() {
        localStorage.removeItem(
            "access_token"
        );

        localStorage.removeItem(
            "refresh_token"
        );
    },
};

export default authService;