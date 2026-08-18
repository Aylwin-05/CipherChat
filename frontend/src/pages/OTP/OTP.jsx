import { useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import toast from "react-hot-toast";

import { useAuth } from "../../context/AuthContext";
import authService from "../../services/authService";

import "../Login/Login.css";
import "./OTP.css";

const RESEND_COOLDOWN = 30;

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

    // -------------------------------------------------
    // Resend cooldown (30s countdown)
    // -------------------------------------------------

    const [secondsLeft, setSecondsLeft] =
        useState(RESEND_COOLDOWN);

    const [resending, setResending] =
        useState(false);

    useEffect(() => {

        if (secondsLeft <= 0) return;

        const timer =
            setTimeout(() => {

                setSecondsLeft(previous =>
                    previous - 1
                );

            }, 1000);

        return () =>
            clearTimeout(timer);

    }, [secondsLeft]);

    // -------------------------------------------------
    // OTP Verification
    // -------------------------------------------------

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

            // -------------------------------------------------
            // 1. Verify OTP with backend
            // -------------------------------------------------

            const response =
                await authService.verifyOTP(
                    email,
                    otp
                );

            // LOG EVERYTHING - for debugging
            console.log("=== OTP VERIFY DEBUG ===");
            console.log("Full response:", response);
            console.log("response.access_token:", response?.access_token);
            console.log("response.user:", response?.user);
            console.log("response type:", typeof response);
            console.log("=======================");

            // -------------------------------------------------
            // 2. Check response - backend returns TokenResponse
            //    with access_token, refresh_token, user (NOT {success: bool})
            // -------------------------------------------------

            if (!response?.access_token) {

                const errorMsg =
                    response?.detail ||
                    response?.message ||
                    "Invalid OTP."

                setError(errorMsg);

                // Show toast with error details
                toast.error(errorMsg);

                // Show detailed error in console
                console.error("OTP verification failed response:", response);

                // Reset OTP field
                setOtp("");

                return;

            }

            // -------------------------------------------------
            // 3. Log in with the access token
            // -------------------------------------------------

            // Save user and token to localStorage for persistence
            await login(response.access_token);

            // Also explicitly store in localStorage
            localStorage.setItem(
                "access_token",
                response.access_token
            );

            // Set user in localStorage for session restoration
            const userData = {

                id: response.user?.id,

                email: response.user?.email,

                username: response.user?.username,

                display_name: response.user?.display_name,

                avatar_url: response.user?.avatar_url,

                is_verified: response.user?.is_verified

            };

            localStorage.setItem(

                "user",

                JSON.stringify(userData)

            );

            // -------------------------------------------------
            // 4. Redirect to dashboard
            // -------------------------------------------------

            // Wait a moment for session to establish, then redirect
            setTimeout(() => {

                navigate("/dashboard", {

                    replace: true,

                });

            }, 3000);

        }

        catch (err) {

            console.error("OTP verify error:", err);

            setError(

                err.response?.data?.detail ||

                err.message ||

                "Invalid OTP."

            );

            // Show toast with error details
            toast.error(

                setError?.()

                    ? setError()

                    : "Invalid OTP. Please try again."

            );

            // Reset OTP field
            setOtp("");

        }

        finally {

            setLoading(false);

        }

    };

    // -------------------------------------------------
    // Resend OTP (only after the cooldown ends)
    // -------------------------------------------------

    async function handleResend() {

        if (
            resending ||
            secondsLeft > 0 ||
            !email
        ) {
            return;
        }

        setResending(true);

        setError("");

        try {

            await authService.sendOTP(
                email
            );

            toast.success(
                "A new code has been sent."
            );

            setOtp("");

            setSecondsLeft(
                RESEND_COOLDOWN
            );

        }

        catch (err) {

            setError(

                err.response?.data?.detail ||

                err.message ||

                "Unable to resend OTP."

            );

            toast.error(

                setError?.()

                    ? setError()

                    : "Unable to resend OTP."

            );

        }

        finally {

            setResending(false);

        }

    }

    // -------------------------------------------------
    // Load user on page mount - restore session from localStorage
    // -------------------------------------------------

    useEffect(() => {

        // Check if user is already logged in (session persisted)
        const storedUser = localStorage.getItem("user");

        if (storedUser) {

            try {

                const user = JSON.parse(storedUser);

                // Restore user state - this will also set accessToken via AuthContext
                login(JSON.stringify(user));

                // Redirect to dashboard if on OTP page
                if (location.pathname === "/otp") {

                    navigate("/dashboard", {

                        replace: true,

                    });

                }

            } catch (error) {

                console.error("Failed to restore session:", error);

                // Clear invalid stored user
                localStorage.removeItem("user");

            }

        }

    }, [location.pathname]);

    // -------------------------------------------------
    // Resend cooldown timer
    // -------------------------------------------------

    useEffect(() => {

        if (secondsLeft <= 0) return;

        const timer =
            setTimeout(() => {

                setSecondsLeft(previous =>
                    previous - 1
                );

            }, 1000);

        return () =>
            clearTimeout(timer);

    }, [secondsLeft]);

    return (

        <div className="auth-bg">

            <div className="auth-orbs" aria-hidden="true">

                <div className="orb orb-a" />

                <div className="orb orb-b" />

                <div className="orb orb-c" />

            </div>

            <div className="auth-card-wrap otp-wrap">

                <div className="auth-card">

                    <button
                        type="button"
                        className="otp-back"
                        onClick={() =>
                            navigate("/login")
                        }
                    >
                        ← Back to login
                    </button>

                    <h1>Verify OTP</h1>

                    <p className="auth-tagline">

                        Enter the 6-digit code sent to

                    </p>

                    <div className="otp-email">

                        {email || "your email"}

                    </div>

                    <form onSubmit={handleVerify}>

                        <div className="field otp-field">

                            <input
                                type="text"
                                maxLength={6}
                                placeholder="••••••"
                                value={otp}
                                onChange={(e) =>
                                    setOtp(
                                        e.target.value.replace(/\D/g, "")
                                    )
                                }
                                inputMode="numeric"
                                autoFocus
                            />

                        </div>

                        {

                            error && (

                                <div className="form-error">

                                    {error}

                                </div>

                            )

                        }

                        <button
                            type="submit"
                            className="btn-primary auth-submit"
                            disabled={loading}
                        >

                            {

                                loading

                                    ? "Verifying..."

                                    : "Verify & Enter"

                            }

                        </button>

                    </form>

                    {/* ---------- resend (with cooldown) ---------- */}
                    <div className="otp-resend">

                        {secondsLeft > 0 ? (

                            <span className="otp-resend-timer">

                                <span
                                    className="otp-ring"
                                    style={{
                                        background:
                                            `conic-gradient(
                                                var(--accent)
                                                ${(secondsLeft / RESEND_COOLDOWN) * 360}deg,
                                                rgba(255, 255, 255, 0.08) 0deg
                                            )`,
                                    }}
                                >

                                    <span
                                        className="otp-ring-inner"
                                    >

                                        {secondsLeft}

                                    </span>

                                </span>

                                Resend code in {secondsLeft}s

                            </span>

                        ) : (

                            <button
                                type="button"
                                className="btn-ghost otp-resend-btn"
                                onClick={handleResend}
                                disabled={resending}
                            >

                                <svg
                                    width="16"
                                    height="16"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                                    <path d="M21 3v6h-6" />
                                </svg>

                                {

                                    resending

                                        ? "Sending…"

                                        : "Resend OTP"

                                }

                            </button>

                        )}

                    </div>

                </div>

            </div>

        </div>

    );

}