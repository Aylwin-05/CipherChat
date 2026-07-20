import { createContext, useContext, useEffect, useState } from "react";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [accessToken, setAccessToken] = useState(
        localStorage.getItem("access_token")
    );
    const [loading, setLoading] = useState(true);

    // ==========================================================
    // Initialize Authentication
    // ==========================================================

    useEffect(() => {
        if (accessToken) {
            setUser({
                authenticated: true,
            });
        }

        setLoading(false);
    }, [accessToken]);

    // ==========================================================
    // Login
    // ==========================================================

    const login = (
        accessToken,
        refreshToken
    ) => {
        localStorage.setItem(
            "access_token",
            accessToken
        );

        localStorage.setItem(
            "refresh_token",
            refreshToken
        );

        setAccessToken(accessToken);

        setUser({
            authenticated: true,
        });
    };

    // ==========================================================
    // Logout
    // ==========================================================

    const logout = () => {
        localStorage.removeItem(
            "access_token"
        );

        localStorage.removeItem(
            "refresh_token"
        );

        setAccessToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                loading,
                login,
                logout,
                accessToken,
                isAuthenticated:
                    user !== null,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(
        AuthContext
    );

    if (!context) {
        throw new Error(
            "useAuth must be used inside AuthProvider"
        );
    }

    return context;
}