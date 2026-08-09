import { useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";

import { useAuth } from "../../context/AuthContext";
import authService from "../../services/authService";

import "./OTP.css";

export default function OTP() {

    const navigate = useNavigate();

    const location = useLocation();

    const { login } = useAuth();

    const email =
        location.state?.email || "";

    const [otp, setOtp] =
        useState("");

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState("");

    const handleVerify = async (e) => {

        e.preventDefault();

        setError("");

        if (otp.length !== 6) {

            setError(
                "OTP must be 6 digits."
            );

            return;

        }

        try {

            setLoading(true);

            const response =
                await authService.verifyOTP(
                    email,
                    otp
                );

// ==========================================
            // Login + Load User Profile
            //
            // The refresh token was already written into the
            // HttpOnly cookie by the server; only the access
            // token is kept (in memory).
            // ==========================================

            await login(
                response.access_token
            );

            navigate(
                "/dashboard",
                {
                    replace: true,
                }
            );

        }

        catch (err) {

            setError(

                err.response?.data?.detail ||

                "Invalid OTP."

            );

        }

        finally {

            setLoading(false);

        }

    };

    return (

        <div className="otp-container">

            <div className="otp-card">

                <h1>

                    Verify OTP

                </h1>

                <p>

                    OTP sent to

                </p>

                <strong>

                    {email}

                </strong>

                <form
                    onSubmit={handleVerify}
                >

                    <input
                        type="text"
                        maxLength={6}
                        placeholder="Enter OTP"
                        value={otp}
                        onChange={(e) =>
                            setOtp(
                                e.target.value
                            )
                        }
                    />

                    {

                        error && (

                            <div className="error">

                                {error}

                            </div>

                        )

                    }

                    <button
                        type="submit"
                        disabled={loading}
                    >

                        {

                            loading

                                ? "Verifying..."

                                : "Verify OTP"

                        }

                    </button>

                </form>

            </div>

        </div>

    );

}