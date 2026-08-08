import {
    createContext,
    useContext,
    useEffect,
    useState,
} from "react";

import authService from "../services/authService";
import keyService from "../services/keyService";
import {
    ensureDeviceRegistered,
    replenishPreKeys,
    wipeDeviceData,
} from "../services/signalService";

import {
    generateIdentityKeys,
} from "../crypto/cryptoService";

import {
    hasKeyPair,
    saveKeyPair,
    getPublicKey,
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

            let signalDevice = null;

            await authService.login(
                accessToken,
                refreshToken,
            );

            // --------------------------------------------------
            // Generate identity only once
            // --------------------------------------------------

            if (!hasKeyPair()) {

                console.log(
                    "Generating RSA identity..."
                );

                const keys =
                    await generateIdentityKeys();

                saveKeyPair(
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

            // --------------------------------------------------
            // Signal device registration (first time only)
            // --------------------------------------------------

            if (!signalDevice) {

                console.log(
                    "Registering Signal device..."
                );

                try {

                    const result =
                        await ensureDeviceRegistered();

                    signalDevice = result;

                    console.log(
                        "Signal device registered:",
                        result.deviceId,
                        result.isPrimary
                            ? "(primary)"
                            : "(secondary)"
                    );

                }

                catch (error) {

                    console.error(
                        "Signal device registration failed:",
                        error
                    );

                }

            }

            // --------------------------------------------------
            // Keep the one-time prekey pool topped up
            // --------------------------------------------------

            try {

                const topUp =
                    await replenishPreKeys();

                if (topUp.replenished > 0) {

                    console.log(
                        `Replenished ${topUp.replenished} one-time prekeys ` +
                        `(${topUp.uploaded} uploaded).`
                    );

                }

            }

            catch (error) {

                console.error(
                    "One-time prekey replenishment failed:",
                    error
                );

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

    const logout = () => {

        // Wipe the local Signal key store (and best-effort
        // remove the device from the server). Fire-and-forget:
        // logout must not block on the network.

        wipeDeviceData()
            .catch((error) =>
                console.error(
                    "Device wipe failed:",
                    error
                )
            );

        authService.logout();

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