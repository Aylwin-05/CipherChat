import axios from "axios";

// Absolute server origin when running outside a normal browser
// origin (Capacitor/WebView builds). Empty in the web app, which
// keeps every URL relative exactly as before.
const SERVER_URL = import.meta.env.VITE_API_URL || "";

const api = axios.create({
    baseURL: `${SERVER_URL}/api/v1`,
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 10000,
    // Required for the refresh-token cookie when the API lives
    // on another origin (native shells); harmless same-origin.
    withCredentials: true,
});

// ==========================================================
// ACCESS TOKEN STORE
//
// The access token lives in memory (and is mirrored to
// localStorage so a page reload keeps the session until the
// token expires).
// ==========================================================

let accessToken =
    localStorage.getItem("access_token");

export function setAccessToken(
    token
) {

    accessToken = token;

    if (token) {

        localStorage.setItem(
            "access_token",
            token
        );

    }

    else {

        localStorage.removeItem(
            "access_token"
        );

    }

}

export function getAccessToken() {

    return accessToken;

}

export function clearAccessToken() {

    setAccessToken(null);

}

// ==========================================================
// REFRESH ACCESS TOKEN
//
// The refresh token lives in an HttpOnly cookie which the
// browser attaches automatically. Returns the new access
// token string, or throws.
// ==========================================================

export async function refreshAccessToken() {

    const response =
        await axios.post(
            `${SERVER_URL}/api/v1/auth/refresh`,
            null,
            { withCredentials: true }
        );

    const newAccessToken =
        response.data.access_token;

    if (!newAccessToken) {

        throw new Error(
            "Refresh returned no access token."
        );

    }

    setAccessToken(newAccessToken);

    return newAccessToken;

}

// ==========================================================
// REQUEST INTERCEPTOR
// ==========================================================

api.interceptors.request.use(

    (config) => {

        const token =
            getAccessToken();

        if (token) {

            config.headers.Authorization =
                `Bearer ${token}`;

        }

        return config;

    },

    (error) => Promise.reject(error)

);

// ==========================================================
// TOKEN REFRESH
// ==========================================================

let isRefreshing = false;

let failedQueue = [];

function processQueue(
    error,
    token = null,
) {

    failedQueue.forEach(
        (promise) => {

            if (error) {

                promise.reject(error);

            }

            else {

                promise.resolve(token);

            }

        }
    );

    failedQueue = [];

}

// ==========================================================
// RESPONSE INTERCEPTOR
// ==========================================================

api.interceptors.response.use(

    (response) => response,

    async (error) => {

        const originalRequest =
            error.config;

        //------------------------------------------------------
        // Access token expired
        //------------------------------------------------------

        if (

            error.response?.status === 401 &&

            !originalRequest._retry

        ) {

            originalRequest._retry = true;

            //--------------------------------------------------

            if (isRefreshing) {

                return new Promise(
                    (
                        resolve,
                        reject,
                    ) => {

                        failedQueue.push({

                            resolve,

                            reject,

                        });

                    }

                ).then(

                    (token) => {

                        originalRequest.headers.Authorization =
                            `Bearer ${token}`;

                        return api(
                            originalRequest
                        );

                    }

                );

            }

            //--------------------------------------------------

            isRefreshing = true;

            try {

                const newAccessToken =
                    await refreshAccessToken();

                originalRequest.headers.Authorization =
                    `Bearer ${newAccessToken}`;

                processQueue(
                    null,
                    newAccessToken
                );

                return api(
                    originalRequest
                );

            }

            catch (refreshError) {

                processQueue(
                    refreshError,
                    null
                );

                clearAccessToken();

                localStorage.removeItem(
                    "refresh_token"
                );

                localStorage.removeItem(
                    "user"
                );

                window.location.href = "/";

                return Promise.reject(
                    refreshError
                );

            }

            finally {

                isRefreshing = false;

            }

        }

        console.error(
            "API Error:",
            error.response?.data ||
            error.message
        );

        return Promise.reject(error);

    }

);

export default api;