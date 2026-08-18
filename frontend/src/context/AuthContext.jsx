import {
    createContext,
    useContext,
    useEffect,
    useState,
} from "react";

import authService from "../services/authService";
import keyService from "../services/keyService";
import recoveryService from "../services/recoveryService";
import {
    ensureDeviceRegistered,
    replenishPreKeys,
    wipeDeviceData,
} from "../services/signalService";

import {
    clearSyncKeyCache,
} from "../crypto/syncCrypto";

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

    // Recovery code state:
    //  - recoveryCode: code just created by THIS registration
    //    (show once so the user can save it)
    //  - needsRecoveryEntry: the account HAS a recovery key but
    //    this browser hasn't unlocked the sync secret yet
    const [recoveryCode, setRecoveryCode] = useState(null);

    const [needsRecoveryEntry, setNeedsRecoveryEntry] = useState(false);

    // ==========================================================
    // Recovery reconciliation after login/boot
    //
    // A fresh registration that created the account's recovery
    // key already auto-unlocked the sync secret; the code must
    // still be shown once. An existing account whose key this
    // browser never unlocked prompts for the code.
    // ==========================================================

    async function reconcileRecovery(profile, registrationResult) {

        if (registrationResult?.recoveryCode) {

            setRecoveryCode(registrationResult.recoveryCode);

            return;

        }

        if (
            profile?.has_recovery_key &&
            !(await recoveryService.hasSyncSecret())
        ) {

            setNeedsRecoveryEntry(true);

        }

    }

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

                return result;

            }

            catch (error) {

                console.error(
                    "Signal device setup failed:",
                    error
                );

                return null;

            }

        }

        async function initialize() {

            try {

                if (accessToken) {

                    const profile =
                        await authService.loadCurrentUser();

                    if (active) setUser(profile);

                    const result =
                        await ensureCryptoSetup();

                    if (active) {

                        await reconcileRecovery(
                            profile,
                            result,
                        );

                    }

                    return;

                }

                const token =
                    await authService.refreshAccessToken();

                if (!active) return;

                setAccessToken(token);

                const profile =
                    await authService.loadCurrentUser();

                setUser(profile);

                const result =
                    await ensureCryptoSetup();

                await reconcileRecovery(
                    profile,
                    result,
                );

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

            // --------------------------------------------------
            // Set access token in memory first
            // --------------------------------------------------

            authService.login(accessToken);

            // --------------------------------------------------
            // Also save to localStorage so it persists across tabs/restarts
            // --------------------------------------------------

            const profile =
                await authService.loadCurrentUser();

            // Save both the user profile AND the access token
            // to localStorage for maximum persistence
            authService.saveUser(profile);

            // Also explicitly store the token for this session
            localStorage.setItem(
                "access_token",
                accessToken
            );

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

                await reconcileRecovery(
                    profile,
                    result,
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
    // Recovery code actions
    // ==========================================================

    const submitRecoveryCode = async (code) => {

        await recoveryService.unlock(code);

        setNeedsRecoveryEntry(false);

        return true;

    };

    const dismissRecoveryEntry = () => {

        setNeedsRecoveryEntry(false);

    };

    const dismissRecoveryCode = () => {

        setRecoveryCode(null);

    };

    // ==========================================================
    // Logout
    // ==========================================================

    const logout = () => {        // Wipe the local Signal key store (and best-effort
        // remove the device from the server). Fire-and-forget:
        // logout must not block on the network.

        clearSyncKeyCache();

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
                recoveryCode,
                needsRecoveryEntry,
                submitRecoveryCode,
                dismissRecoveryEntry,
                dismissRecoveryCode,
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