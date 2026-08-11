import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import App from "./App";
import "./index.css";
import { AuthProvider } from "./context/AuthContext";
import ErrorBoundary from "./components/layout/ErrorBoundary";
import { applyTheme, getTheme } from "./utils/theme";

applyTheme(getTheme());

ReactDOM.createRoot(
    document.getElementById("root")
).render(
    <React.StrictMode>
        <ErrorBoundary>
            <BrowserRouter>
                <AuthProvider>
                    <App />
                    <Toaster position="top-right" reverseOrder={false} />
                </AuthProvider>
            </BrowserRouter>
        </ErrorBoundary>
    </React.StrictMode>
);