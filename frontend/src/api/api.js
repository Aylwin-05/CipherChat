import axios from "axios";

const api = axios.create({
    baseURL: "http://127.0.0.1:8000/api/v1",
    headers: {
        "Content-Type": "application/json",
    },
    timeout: 10000,
});

// ==========================================================
// REQUEST INTERCEPTOR
// ==========================================================

api.interceptors.request.use(

    (config) => {

        const token =
            localStorage.getItem(
                "access_token"
            );

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

                const refreshToken =
                    localStorage.getItem(
                        "refresh_token"
                    );

                if (!refreshToken) {

                    throw new Error(
                        "No refresh token."
                    );

                }

                const response =
                    await axios.post(

                        "http://127.0.0.1:8000/api/v1/auth/refresh",

                        {

                            refresh_token:
                                refreshToken,

                        }

                    );

                const newAccessToken =
                    response.data.access_token;

                localStorage.setItem(

                    "access_token",

                    newAccessToken

                );

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

                localStorage.removeItem(
                    "access_token"
                );

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