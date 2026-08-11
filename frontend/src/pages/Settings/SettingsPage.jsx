import { useRef, useState } from "react";

import toast from "react-hot-toast";

import UserAvatar, {
    bustAvatarCache,
} from "../../components/UserAvatar";

import userService from "../../services/userService";

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
