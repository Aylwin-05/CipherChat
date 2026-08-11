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

    const [accessToken, setAccessToken] = useState(null);

    // ==========================================================
    // Initialize Authentication
    //
    // Boot restore: if there is no in-memory access token (fresh
    // page load), try to renew the session from the HttpOnly
    // refresh cookie. If the cookie is gone or expired, the user
    // silently lands on the login page.
    // ==========================================================

    useEffect(() => {

        let active = true;

        // --------------------------------------------------
        // Register the Signal device on every boot (no-op if
        // already registered). Accounts created before the
        // device feature, or whose local key store was wiped,
        // self-heal here instead of needing a manual re-login.
        // --------------------------------------------------

        async function ensureCryptoSetup() {

            try {

                const result =
                    await ensureDeviceRegistered();

                if (result.generated) {

                    console.log(
                        "Signal device registered:",
                        result.deviceId,
                        result.isPrimary
                            ? "(primary)"
                            : "(secondary)"
                    );

                }

                await replenishPreKeys();

            }

            catch (error) {

                console.error(
                    "Signal device setup failed:",
                    error
                );

            }

        }

        async function initialize() {

            try {

                if (accessToken) {

                    const profile =
                        await authService.loadCurrentUser();

                    if (active) setUser(profile);

                    await ensureCryptoSetup();

                    return;

                }

                const token =
                    await authService.refreshAccessToken();

                if (!active) return;

                setAccessToken(token);

                const profile =
                    await authService.loadCurrentUser();

                setUser(profile);

                await ensureCryptoSetup();

            }

            catch (error) {

                console.error(error);

                if (active) {

                    authService.logout();

                    setUser(null);

                }

            }

            finally {

                if (active) setLoading(false);

            }

        }

        initialize();

        return () => { active = false; };

    }, []);

    // ==========================================================
    // Login
    // ==========================================================

    const login = async (
        accessToken,
    ) => {

        try {

            authService.login(accessToken);

            const profile =
                await authService.loadCurrentUser();

            setUser(profile);

            // --------------------------------------------------
            // Generate identity only once
            // --------------------------------------------------

            if (!hasKeyPair()) {

                const keys =
                    await generateIdentityKeys();

                saveKeyPair(
                    keys.publicKey,
                    keys.privateKey,
                );

                await keyService.uploadPublicKey(
                    keys.publicKey
                );

            }

            else {

                // Optional safety check: upload again if the
                // backend lost it.
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

            try {

                const result =
                    await ensureDeviceRegistered();

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
    // Update Current User (used by Settings after profile edits)
    // ==========================================================

    const updateUser = (updatedUser) => {

        authService.saveUser(updatedUser);

        setUser(updatedUser);

    };

    // ==========================================================
    // Logout
    // ==========================================================

    const logout = () => {        // Wipe the local Signal key store (and best-effort
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
                updateUser,
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