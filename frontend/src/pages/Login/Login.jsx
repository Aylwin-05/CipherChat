import { useState } from "react";
import { useNavigate } from "react-router-dom";

import authService from "../../services/authService";

import "./Login.css";

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
        <div className="login-container">
            <div className="login-card">
                <h1>CipherChat</h1>

                <p>
                    Secure Messaging
                </p>

                <form
                    onSubmit={
                        handleSubmit
                    }
                >
                    <input
                        type="email"
                        placeholder="Email Address"
                        value={email}
                        onChange={(e) =>
                            setEmail(
                                e.target
                                    .value
                            )
                        }
                    />

                    {error && (
                        <div className="error">
                            {error}
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={
                            loading
                        }
                    >
                        {loading
                            ? "Sending..."
                            : "Send OTP"}
                    </button>
                </form>
            </div>
        </div>
    );
}