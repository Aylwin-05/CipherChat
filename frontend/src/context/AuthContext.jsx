import {
    createContext,
    useContext,
    useEffect,
    useState,
} from "react";

import authService from "../services/authService";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {

    const [user, setUser] = useState(
        authService.getStoredUser()
    );

    const [loading, setLoading] = useState(true);

    const [accessToken, setAccessToken] = useState(
        authService.getAccessToken()
    );

    // ==========================================================
    // Initialize Authentication
    // ==========================================================

    useEffect(() => {

        async function initialize() {

            if (!accessToken) {

                setLoading(false);

                return;

            }

            try {

                const profile =
                    await authService.loadCurrentUser();

                setUser(profile);

            }

            catch (error) {

                console.error(
                    "Authentication failed:",
                    error
                );

                authService.logout();

                setUser(null);

                setAccessToken(null);

            }

            finally {

                setLoading(false);

            }

        }

        initialize();

    }, [accessToken]);

    // ==========================================================
    // Login
    // ==========================================================

    const login = async (
        accessToken,
        refreshToken,
    ) => {

        const profile =
            await authService.login(
                accessToken,
                refreshToken,
            );

        setAccessToken(accessToken);

        setUser(profile);

    };

    // ==========================================================
    // Logout
    // ==========================================================

    const logout = () => {

        authService.logout();

        setAccessToken(null);

        setUser(null);

    };

    return (

        <AuthContext.Provider
            value={{

                user,

                loading,

                accessToken,

                login,

                logout,

                isAuthenticated:
                    !!user,

            }}
        >

            {children}

        </AuthContext.Provider>

    );

}

export function useAuth() {

    const context =
        useContext(AuthContext);

    if (!context) {

        throw new Error(
            "useAuth must be used within AuthProvider"
        );

    }

    return context;

}