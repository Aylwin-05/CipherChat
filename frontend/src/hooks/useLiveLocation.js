import { useCallback, useEffect, useRef, useState } from "react";

import websocketService from "../services/websocketService";

const DURATION_MS = {
    "15m": 15 * 60 * 1000,
    "1h":  60 * 60 * 1000,
    "8h":  8 * 60 * 60 * 1000,
};

const UPDATE_INTERVAL_MS = 10_000;

export default function useLiveLocation(
    conversationId,
) {

    const [sharing, setSharing] = useState(false);

    const [error, setError] = useState(null);

    const watchIdRef = useRef(null);

    const timerRef = useRef(null);

    const expiryRef = useRef(null);

    const clearTimers = useCallback(() => {

        if (watchIdRef.current !== null) {

            navigator.geolocation.clearWatch(
                watchIdRef.current,
            );

            watchIdRef.current = null;

        }

        if (timerRef.current !== null) {

            clearInterval(timerRef.current);

            timerRef.current = null;

        }

        if (expiryRef.current !== null) {

            clearTimeout(expiryRef.current);

            expiryRef.current = null;

        }

    }, []);

    const stop = useCallback(() => {

        clearTimers();

        setSharing(false);

    }, [clearTimers]);

    const start = useCallback((duration = "15m") => {

        if (!conversationId) return;

        if (!navigator.geolocation) {

            setError(new Error("Geolocation not supported"));

            return;

        }

        stop();

        setError(null);

        setSharing(true);

        const durationMs = DURATION_MS[duration] ?? DURATION_MS["15m"];

        const send = (position) => {

            const { latitude, longitude } =
                position.coords;

            websocketService.sendLocationUpdate(
                conversationId,
                latitude,
                longitude,
            );

        };

        const watchId = navigator.geolocation.watchPosition(
            send,
            (err) => {

                setError(err);

                stop();

            },
            {
                enableHighAccuracy: true,
                maximumAge: 5_000,
                timeout: 15_000,
            },
        );

        watchIdRef.current = watchId;

        timerRef.current = setInterval(() => {

            navigator.geolocation.getCurrentPosition(
                send,
                () => {},
                {
                    enableHighAccuracy: true,
                    maximumAge: 5_000,
                    timeout: 10_000,
                },
            );

        }, UPDATE_INTERVAL_MS);

        expiryRef.current = setTimeout(
            stop,
            durationMs,
        );

    }, [conversationId, stop]);

    useEffect(() => {

        return () => {

            clearTimers();

        };

    }, [clearTimers]);

    return {
        sharing,
        start,
        stop,
        error,
    };

}
