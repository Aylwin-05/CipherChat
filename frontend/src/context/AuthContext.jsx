import {
    createContext,
    useContext,
    useEffect,
    useState,
} from "react";

import authService from "../services/authService";
import keyService from "../services/keyService";

import {
    generateIdentityKeys,
} from "../crypto/cryptoService";

import {
    hasKeyPair,
    saveKeyPair,
    getPublicKey,
    clearKeyPair,
} from "../crypto/keyStorage";

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

                console.error(error);

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

        try {

            console.log("========== LOGIN ==========");

            await authService.login(
                accessToken,
                refreshToken,
            );

            // --------------------------------------------------
            // Generate identity only once
            // --------------------------------------------------

            if (!(await hasKeyPair())) {

                console.log(
                    "Generating RSA identity..."
                );

                const keys =
                    await generateIdentityKeys();

                await saveKeyPair(
                    keys.publicKey,
                    keys.privateKey,
                );

                console.log(
                    "Uploading public key..."
                );

                await keyService.uploadPublicKey(
                    keys.publicKey
                );

                console.log(
                    "Public key uploaded."
                );

            }

            else {

                console.log(
                    "Key pair already exists."
                );

                // Optional safety check
                // Upload again if backend lost it

                try {

                    await keyService.uploadPublicKey(
                        getPublicKey()
                    );

                }

                catch (e) {

                    console.log(
                        "Public key already exists on server."
                    );

                }

            }

            setAccessToken(
                accessToken
            );
        }

        catch (error) {

            console.error(error);

            throw error;

        };

    };

    // ==========================================================
    // Logout
    // ==========================================================

    const logout = async () => {

        authService.logout();

        await clearKeyPair();

        setUser(null);

        setAccessToken(null);

    };

    return (

        <AuthContext.Provider
            value={{
                user,
                loading,
                accessToken,
                login,
                logout,
                isAuthenticated: !!user,
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