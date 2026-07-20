import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({
    children,
}) {
    const {
        loading,
        isAuthenticated,
    } = useAuth();

    if (loading) {
        return (
            <h2
                style={{
                    textAlign:
                        "center",
                    marginTop:
                        "100px",
                }}
            >
                Loading...
            </h2>
        );
    }

    if (!isAuthenticated) {
        return (
            <Navigate
                to="/login"
                replace
            />
        );
    }

    return children;
}