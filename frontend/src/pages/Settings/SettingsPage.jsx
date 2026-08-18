import {
    useEffect,
    useRef,
    useState,
} from "react";

import toast from "react-hot-toast";

import UserAvatar, {
    bustAvatarCache,
} from "../../components/UserAvatar";

import userService from "../../services/userService";

import recoveryService from "../../services/recoveryService";

import { signalKeyStore } from "../../crypto/signal/keyStore";

import { useAuth } from "../../context/AuthContext";

import { getTheme, setTheme } from "../../utils/theme";

import "./SettingsPage.css";

const THEME_OPTIONS = [
    {
        id: "blue",
        label: "Blue",
        description: "Nebula blue — the signature CipherChat look.",
        colors: ["#7c5cff", "#22d3ee"],
    },
    {
        id: "dark",
        label: "Dark",
        description: "Neutral deep black, easy on the eyes.",
        colors: ["#16181d", "#2a2d35"],
    },
    {
        id: "light",
        label: "Light",
        description: "Bright and clean for daytime use.",
        colors: ["#ffffff", "#dbe4f0"],
    },
];

export default function SettingsPage() {

    const {
        user,
        updateUser,
        logout,
    } = useAuth();

    const fileInputRef = useRef(null);

    const [username, setUsername] = useState(
        user?.username ?? ""
    );

    const [displayName, setDisplayName] = useState(
        user?.display_name ?? ""
    );

    const [saving, setSaving] = useState(false);

    const [uploading, setUploading] = useState(false);

    const [theme, setThemeState] = useState(getTheme());

    const [confirmLogout, setConfirmLogout] = useState(false);

    // ==========================================================
    // Support: recover a lost/forgotten recovery code
    //
    // The request is limited to 3 per 10 minutes per email; the
    // ring timer below mirrors that window (the server reports
    // the remaining seconds).
    // ==========================================================

    const [recoveryBusy, setRecoveryBusy] = useState(false);

    const [recoverySent, setRecoverySent] = useState(false);

    const [recoveryHasSecret, setRecoveryHasSecret] = useState(false);

    const [recoveryRemaining, setRecoveryRemaining] = useState(3);

    const [recoveryCooldown, setRecoveryCooldown] = useState(0);

    const [recoveryError, setRecoveryError] = useState(null);

    const [confirmFreshKey, setConfirmFreshKey] = useState(false);

    // Enter-an-existing-code box (already-logged-in unlock)
    const [unlockCode, setUnlockCode] = useState("");

    const [unlockBusy, setUnlockBusy] = useState(false);

    const [unlockError, setUnlockError] = useState(null);

    const [unlocked, setUnlocked] = useState(false);

    useEffect(() => {

        recoveryService.hasSyncSecret()
            .then(setRecoveryHasSecret)
            .catch(() => {});

    }, []);

    useEffect(() => {

        if (recoveryCooldown <= 0) return;

        const timer = setTimeout(
            () => setRecoveryCooldown(
                previous => previous - 1
            ),
            1000,
        );

        return () => clearTimeout(timer);

    }, [recoveryCooldown]);

    async function handleUnlockCode(event) {

        event.preventDefault();

        if (unlockBusy) return;

        setUnlockBusy(true);

        setUnlockError(null);

        try {

            await recoveryService.unlock(unlockCode);

            setUnlocked(true);

            setRecoveryHasSecret(true);

            toast.success(
                "History unlocked on this browser."
            );

        }
        catch (err) {

            setUnlockError(
                err?.message ||
                "That code didn't work. Check it and try again."
            );

        }
        finally {

            setUnlockBusy(false);

        }

    }

    function formatCooldown(seconds) {

        const m = Math.floor(seconds / 60);

        const s = seconds % 60;

        return `${m}:${String(s).padStart(2, "0")}`;

    }

    async function handleRecoverCode() {

        if (
            recoveryBusy ||
            (
                recoveryRemaining <= 0 &&
                recoveryCooldown > 0
            )
        ) {
            return;
        }

        setRecoveryBusy(true);

        setRecoveryError(null);

        setConfirmFreshKey(false);

        try {

            // Re-wrap the SAME secret when this browser has it
            // (lossless), otherwise mint a fresh account key.
            const secret =
                await signalKeyStore.getSyncSecret();

            const data =
                await recoveryService.requestRecoveryCode(
                    secret
                );

            setRecoverySent(true);

            setRecoveryRemaining(data.remaining);

            setRecoveryCooldown(data.retry_after);

            toast.success(
                "Recovery link sent — check your inbox."
            );

        }
        catch (err) {

            const retryAfter =
                err?.response?.headers?.["retry-after"];

            if (retryAfter) {

                setRecoveryCooldown(Number(retryAfter));

                setRecoveryRemaining(0);

                setRecoveryError(
                    "You have used all 3 requests for this " +
                    "10-minute window. Try again when the " +
                    "timer reaches zero."
                );

            }
            else {

                setRecoveryError(
                    err?.response?.data?.detail ||
                    err?.message ||
                    "Could not request the recovery link."
                );

            }

        }
        finally {

            setRecoveryBusy(false);

        }

    }

    // ==========================================================
    // Save profile (username + display name)
    // ==========================================================

    async function handleSaveProfile(event) {
        event.preventDefault();

        if (saving) return;

        setSaving(true);

        try {
            const updated =
                await userService.updateProfile({
                    username: username.trim(),
                    display_name: displayName.trim(),
                });

            updateUser(updated);

            toast.success("Profile updated.");
        }
        catch (error) {
            const detail =
                error.response?.data?.detail ??
                "Unable to update profile.";

            toast.error(detail);
        }
        finally {
            setSaving(false);
        }
    }

    // ==========================================================
    // Avatar upload
    // ==========================================================

    async function handleAvatarChange(event) {
        const file = event.target.files?.[0];

        if (!file) return;

        if (uploading) return;

        if (!file.type.startsWith("image/")) {
            toast.error("Please choose an image file.");
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            toast.error("Avatar must be smaller than 5 MB.");
            return;
        }

        setUploading(true);

        try {
            const updated =
                await userService.uploadAvatar(file);

            updateUser(updated);

            bustAvatarCache(user.id);

            toast.success("Avatar updated.");
        }
        catch (error) {
            const detail =
                error.response?.data?.detail ??
                "Unable to upload avatar.";

            toast.error(detail);
        }
        finally {
            setUploading(false);

            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
        }
    }

    // ==========================================================
    // Theme
    // ==========================================================

    function handleThemeChange(themeId) {
        setTheme(themeId);

        setThemeState(themeId);
    }

    // ==========================================================
    // Logout
    // ==========================================================

    function handleLogout() {
        logout();
    }

    return (

        <div className="settings-page">

            <div className="settings-header">

                <h2>Settings</h2>

                <p>
                    Manage your profile, appearance and account.
                </p>

            </div>

            {/* ------- profile ------- */}

            <section className="settings-card">

                <div className="settings-card-head">

                    <h3>Profile</h3>

                    <p>
                        Your name and avatar are visible to your
                        friends.
                    </p>

                </div>

                <div className="profile-row">

                    <div className="profile-avatar-wrap">

                        <UserAvatar
                            user={user}
                            className="settings-avatar"
                        />

                        {uploading && (
                            <span className="settings-avatar-badge spinner spinner-sm" />
                        )}

                    </div>

                    <div className="profile-avatar-actions">

                        <button
                            type="button"
                            className="btn-ghost"
                            disabled={uploading}
                            onClick={() =>
                                fileInputRef.current?.click()
                            }
                        >
                            Change avatar
                        </button>

                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            hidden
                            onChange={handleAvatarChange}
                        />

                        <small>
                            JPG, PNG, WebP or GIF up to 5 MB.
                        </small>

                    </div>

                </div>

                <form
                    className="settings-form"
                    onSubmit={handleSaveProfile}
                >

                    <div className="settings-field">

                        <label htmlFor="settings-username">
                            Username
                        </label>

                        <input
                            id="settings-username"
                            type="text"
                            value={username}
                            onChange={(e) =>
                                setUsername(e.target.value)
                            }
                            minLength={3}
                            maxLength={30}
                            pattern="[a-zA-Z0-9_.-]+"
                            required
                            autoComplete="off"
                        />

                        <small>
                            3–30 characters: letters, numbers, . _ -
                        </small>

                    </div>

                    <div className="settings-field">

                        <label htmlFor="settings-display-name">
                            Display name
                        </label>

                        <input
                            id="settings-display-name"
                            type="text"
                            value={displayName}
                            onChange={(e) =>
                                setDisplayName(e.target.value)
                            }
                            minLength={2}
                            maxLength={50}
                            required
                            autoComplete="off"
                        />

                        <small>
                            What your friends see in chats.
                        </small>

                    </div>

                    <div className="settings-actions">

                        <button
                            type="submit"
                            className="btn-primary"
                            disabled={saving || uploading}
                        >
                            {saving ? "Saving…" : "Save changes"}
                        </button>

                    </div>

                </form>

            </section>

            {/* ------- appearance ------- */}

            <section className="settings-card">

                <div className="settings-card-head">

                    <h3>Appearance</h3>

                    <p>
                        Pick the CipherChat theme you like.
                    </p>

                </div>

                <div className="theme-grid">

                    {THEME_OPTIONS.map((option) => {

                        const active = theme === option.id;

                        return (

                            <button
                                key={option.id}
                                type="button"
                                className={
                                    active
                                        ? "theme-option active"
                                        : "theme-option"
                                }
                                onClick={() =>
                                    handleThemeChange(option.id)
                                }
                            >

                                <span
                                    className="theme-swatch"
                                    style={{
                                        background: `linear-gradient(135deg, ${option.colors[0]}, ${option.colors[1]})`,
                                    }}
                                />

                                <span className="theme-meta">

                                    <strong>{option.label}</strong>

                                    <small>{option.description}</small>

                                </span>

                                <span className="theme-check">
                                    {active ? "✓" : ""}
                                </span>

                            </button>

                        );

                    })}

                </div>

            </section>

            {/* ------- account ------- */}

            <section className="settings-card support-zone">

                <div className="settings-card-head">

                    <h3>Support</h3>

                    <p>
                        Lost or deleted your recovery code? We can
                        send you a new one — after confirming it
                        is really you.
                    </p>

                </div>

                {recoverySent ? (

                    <div className="settings-actions">

                        <div className="recovery-support-note">
                            A recovery link has been sent to your
                            email. Open it, enter the verification
                            code, and your new recovery code will be
                            shown on screen. It replaces the old one
                            (which stops working) and restores the
                            same synced history.
                        </div>

                    </div>

                ) : !recoveryHasSecret && confirmFreshKey ? (

                    <div className="settings-actions">

                        <div className="logout-confirm">
                            <span>
                                This browser has not unlocked the sync
                                secret yet. Requesting from here will
                                create a <strong>new account key</strong> —
                                history synced before this moment won&apos;t
                                be readable on future browsers (it stays
                                readable on browsers that already have
                                the old key). If you have the app open on
                                another device, request from there instead.
                            </span>

                            <div className="logout-actions">
                                <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() =>
                                        setConfirmFreshKey(false)
                                    }
                                >
                                    Cancel
                                </button>

                                <button
                                    type="button"
                                    className="btn-danger"
                                    onClick={handleRecoverCode}
                                    disabled={recoveryBusy}
                                >
                                    {recoveryBusy
                                        ? "Sending…"
                                        : "Request new key"}
                                </button>
                            </div>
                        </div>

                    </div>

                ) : (

                    <div className="settings-actions">

                        {recoveryError && (
                            <p className="recovery-support-error">
                                {recoveryError}
                            </p>
                        )}

                        {recoveryCooldown > 0 ? (
                            <div className="recovery-support-timer">
                                <div
                                    className="recovery-timer-ring"
                                    style={{
                                        background:
                                            `conic-gradient(var(--accent) ` +
                                            `${(recoveryCooldown / 600) * 360}deg, ` +
                                            `rgba(127, 127, 127, 0.25) 0deg)`,
                                    }}
                                >
                                    <span>
                                        {formatCooldown(
                                            recoveryCooldown
                                        )}
                                    </span>
                                </div>

                                <div className="recovery-timer-text">
                                    {recoveryRemaining > 0
                                        ? `${recoveryRemaining} of 3 ` +
                                          "requests left this window " +
                                          `(resets in ${formatCooldown(
                                              recoveryCooldown
                                          )})`
                                        : "Limit reached — you can " +
                                          "request again when the " +
                                          "timer reaches zero"}
                                </div>
                            </div>
                        ) : null}

                        <button
                            type="button"
                            className="btn-primary settings-support-btn"
                            onClick={() => {

                                if (recoveryHasSecret) {

                                    handleRecoverCode();

                                }
                                else {

                                    setConfirmFreshKey(true);

                                }

                            }}
                            disabled={
                                recoveryBusy ||
                                (
                                    recoveryRemaining <= 0 &&
                                    recoveryCooldown > 0
                                )
                            }
                        >
                            {recoveryBusy
                                ? "Sending…"
                                : "Recover my recovery code"}
                        </button>

                        {!recoveryHasSecret && !confirmFreshKey && (
                            <p className="recovery-support-hint">
                                This browser hasn&apos;t unlocked the sync
                                secret, so requesting here creates a new
                                account key. Request from a browser that
                                already has your history to keep it intact.
                            </p>
                        )}

                        {!recoveryHasSecret && (
                            <div className="recovery-unlock-box">
                                <details>
                                    <summary>
                                        Already have your code? Unlock
                                        this browser
                                    </summary>

                                    <form
                                        className="recovery-unlock-form"
                                        onSubmit={handleUnlockCode}
                                    >
                                        <input
                                            type="text"
                                            className="recovery-unlock-input"
                                            placeholder="XXXXXX-XXXXXX-XXXXXX-XXXXXX"
                                            value={unlockCode}
                                            onChange={event =>
                                                setUnlockCode(
                                                    event.target.value.toUpperCase()
                                                )
                                            }
                                            spellCheck={false}
                                        />

                                        <button
                                            type="submit"
                                            className="btn-ghost"
                                            disabled={
                                                unlockBusy ||
                                                unlockCode.length < 20
                                            }
                                        >
                                            {unlockBusy
                                                ? "Unlocking…"
                                                : "Unlock"}
                                        </button>
                                    </form>

                                    {unlockError && (
                                        <p className="recovery-support-error">
                                            {unlockError}
                                        </p>
                                    )}

                                    {unlocked && (
                                        <p className="recovery-unlock-ok">
                                            This browser is now unlocked —
                                            the full history is readable
                                            here.
                                        </p>
                                    )}
                                </details>
                            </div>
                        )}

                    </div>

                )}

            </section>

            <section className="settings-card danger-zone">

                <div className="settings-card-head">

                    <h3>Account</h3>

                    <p>
                        Log out of CipherChat on this device.
                    </p>

                </div>

                <div className="settings-actions">

                    {confirmLogout ? (

                        <div className="logout-confirm">

                            <span>
                                Log out? Your secure keys on this
                                device will be removed.
                            </span>

                            <div className="logout-actions">

                                <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() =>
                                        setConfirmLogout(false)
                                    }
                                >
                                    Cancel
                                </button>

                                <button
                                    type="button"
                                    className="btn-danger"
                                    onClick={handleLogout}
                                >
                                    Log out
                                </button>

                            </div>

                        </div>

                    ) : (

                        <button
                            type="button"
                            className="btn-danger"
                            onClick={() =>
                                setConfirmLogout(true)
                            }
                        >
                            Log out
                        </button>

                    )}

                </div>

            </section>

        </div>

    );

}
