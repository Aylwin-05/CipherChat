import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import App from "./App";
import "./index.css";
import "./styles/mobile.css";
import { AuthProvider } from "./context/AuthContext";
import ErrorBoundary from "./components/layout/ErrorBoundary";
import { applyTheme, getTheme } from "./utils/theme";
import { registerServiceWorker } from "./services/pushService";

applyTheme(getTheme());

// Register the service worker for Web Push notifications.
// Idempotent; safe to run before auth (subscription itself is
// authenticated later).
void registerServiceWorker();

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