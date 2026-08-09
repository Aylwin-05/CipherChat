import axios from "axios";

const API_BASE_URL =
    import.meta.env.VITE_API_URL || "/api/v1";

// ==========================================================
// ACCESS TOKEN — memory only
// ==========================================================
//
// The access token is kept in a module variable so it is never
// recoverable from localStorage/XSS. The refresh token lives
// exclusively in the server's HttpOnly cookie and is rotated on
// every refresh, so it never needs client-side storage either.

let accessToken = null;

export function setAccessToken(token) {
    accessToken = token || null;
}

export function getAccessToken() {
    return accessToken;
}

export function clearAccessToken() {
    accessToken = null;
}

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 10000,
    withCredentials: true,
});

// Raw instance for the refresh call itself so the response
// interceptor (which also fires on 401) never loops.
const apiWithoutInterceptors = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 10000,
    withCredentials: true,
});

// ==========================================================
// REQUEST INTERCEPTOR
// ==========================================================

api.interceptors.request.use(

    (config) => {

        const token = getAccessToken();

        if (token) {

            config.headers.Authorization =
                `Bearer ${token}`;

        }

        return config;

    },

    (error) => Promise.reject(error)

);

// ==========================================================
// TOKEN REFRESH (via HttpOnly cookie)
//
// Single-flight: concurrent callers (React StrictMode double
// effects, parallel 401 retries) share ONE refresh request.
// Without this, two parallel rotations of the same token would
// trip the server's reuse detector and revoke the whole family.
// ==========================================================

let refreshInFlight = null;

async function refreshAccessToken() {

    if (refreshInFlight) {

        return refreshInFlight;

    }

    refreshInFlight = (async () => {

        const response =
            await apiWithoutInterceptors.post(
                "/auth/refresh",
                {},
            );

        setAccessToken(
            response.data.access_token
        );

        return response.data.access_token;

    })();

    try {

        return await refreshInFlight;

    }

    finally {

        refreshInFlight = null;

    }

}

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

export { refreshAccessToken };