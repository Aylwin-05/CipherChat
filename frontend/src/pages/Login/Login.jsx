import { useState } from "react";
import { useNavigate } from "react-router-dom";

import authService from "../../services/authService";

import "./Login.css";

function ShieldLogo() {
    return (
        <svg
            className="shield-mark auth-logo-mark"
            width="46"
            height="46"
            viewBox="0 0 32 32"
            fill="none"
        >
            <defs>
                <linearGradient
                    id="lg"
                    x1="0"
                    y1="0"
                    x2="1"
                    y2="1"
                >
                    <stop offset="0" stopColor="#7c5cff" />
                    <stop offset="1" stopColor="#22d3ee" />
                </linearGradient>
            </defs>
            <path
                d="M16 2l12 4v8c0 8-5 14-12 16C9 28 4 22 4 14V6z"
                fill="url(#lg)"
            />
            <path
                d="M12 13.5h8M12 17.5h5M12 21.5h8"
                stroke="#fff"
                strokeWidth="1.6"
                strokeLinecap="round"
            />
        </svg>
    );
}

export default function Login() {
    const navigate = useNavigate();

    const [email, setEmail] = useState("");

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState("");

    const handleSubmit = async (e) => {
        e.preventDefault();

        setError("");

        if (!email.trim()) {
            setError(
                "Please enter your email."
            );
            return;
        }

        try {
            setLoading(true);

            await authService.sendOTP(
                email
            );

            navigate("/otp", {
                state: {
                    email,
                },
            });
        } catch (err) {
            setError(
                err.response?.data?.detail ||
                    "Unable to send OTP."
            );
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-bg">
            <div className="auth-orbs" aria-hidden="true">
                <div className="orb orb-a" />
                <div className="orb orb-b" />
                <div className="orb orb-c" />
            </div>

            <div className="auth-card-wrap">
                <div className="auth-card">
                    <ShieldLogo />

                    <h1>Nexara</h1>

                    <p className="auth-tagline">
                        End-to-end encrypted messaging,
                        <br />
                        protected by the Signal protocol.
                    </p>

                    <form onSubmit={handleSubmit}>
                        <div className="field">
                            <svg
                                width="18"
                                height="18"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                strokeLinecap="round"
                            >
                                <rect
                                    x="3"
                                    y="5"
                                    width="18"
                                    height="14"
                                    rx="3"
                                />
                                <path d="m3 7 9 6 9-6" />
                            </svg>

                            <input
                                type="email"
                                placeholder="Email Address"
                                value={email}
                                onChange={(e) =>
                                    setEmail(
                                        e.target.value
                                    )
                                }
                                autoFocus
                            />
                        </div>

                        {error && (
                            <div className="form-error">
                                {error}
                            </div>
                        )}

                        <button
                            type="submit"
                            className="btn-primary auth-submit"
                            disabled={loading}
                        >
                            {loading
                                ? "Sending..."
                                : "Continue"}
                        </button>
                    </form>

                    <div className="auth-features">
                        <span>🔐 Signal-protocol E2EE</span>
                        <span>🕊 No plaintext stored</span>
                        <span>⚡ Real-time delivery</span>
                    </div>
                </div>
            </div>
        </div>
    );
}