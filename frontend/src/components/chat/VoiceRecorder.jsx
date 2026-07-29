import { useEffect, useRef, useState } from "react";

export default function VoiceRecorder({
    onRecorded,
}) {

    const [recording, setRecording] =
        useState(false);

    const [seconds, setSeconds] =
        useState(0);

    const mediaRecorderRef =
        useRef(null);

    const streamRef =
        useRef(null);

    const chunksRef =
        useRef([]);

    const timerRef =
        useRef(null);

    // ======================================================
    // Start Recording
    // ======================================================

    async function startRecording() {

        try {

            const stream =
                await navigator.mediaDevices.getUserMedia({

                    audio: true,

                });

            streamRef.current =
                stream;

            chunksRef.current = [];

            const recorder =
                new MediaRecorder(stream);

            mediaRecorderRef.current =
                recorder;

            recorder.ondataavailable =
                (event) => {

                    if (
                        event.data &&
                        event.data.size > 0
                    ) {

                        chunksRef.current.push(
                            event.data
                        );

                    }

                };

            recorder.onstop =
                async () => {

                    const blob =
                        new Blob(

                            chunksRef.current,

                            {
                                type:
                                    recorder.mimeType ||
                                    "audio/webm",
                            }

                        );

                    const file =
                        new File(

                            [blob],

                            `voice_${Date.now()}.webm`,

                            {
                                type:
                                    blob.type,
                            }

                        );

                    onRecorded(file);

                    stream
                        .getTracks()
                        .forEach(
                            track =>
                                track.stop()
                        );

                };

            recorder.start();

            setRecording(true);

            setSeconds(0);

            timerRef.current =
                setInterval(() => {

                    setSeconds(
                        previous =>
                            previous + 1
                    );

                }, 1000);

        }

        catch (error) {

            console.error(error);

            alert(
                "Microphone permission denied."
            );

        }

    }

    // ======================================================
    // Stop Recording
    // ======================================================

    function stopRecording() {

        if (
            mediaRecorderRef.current &&
            recording
        ) {

            mediaRecorderRef.current.stop();

        }

        clearInterval(
            timerRef.current
        );

        setRecording(false);

    }

    // ======================================================
    // Cancel Recording
    // ======================================================

    function cancelRecording() {

        if (
            mediaRecorderRef.current &&
            recording
        ) {

            mediaRecorderRef.current.stop();

        }

        chunksRef.current = [];

        clearInterval(
            timerRef.current
        );

        streamRef.current
            ?.getTracks()
            .forEach(
                track => track.stop()
            );

        setRecording(false);

        setSeconds(0);

    }

    // ======================================================
    // Cleanup
    // ======================================================

    useEffect(() => {

        return () => {

            clearInterval(
                timerRef.current
            );

            streamRef.current
                ?.getTracks()
                .forEach(
                    track => track.stop()
                );

        };

    }, []);

    const minutes =
        String(
            Math.floor(seconds / 60)
        ).padStart(2, "0");

    const secs =
        String(
            seconds % 60
        ).padStart(2, "0");

    // ======================================================
    // UI
    // ======================================================

    if (!recording) {

        return (

            <button
                type="button"
                onClick={startRecording}
            >
                🎤
            </button>

        );

    }

    return (

        <div
            className="voice-recorder"
        >

            <span>

                🔴 {minutes}:{secs}

            </span>

            <button
                type="button"
                onClick={stopRecording}
            >
                ■
            </button>

            <button
                type="button"
                onClick={cancelRecording}
            >
                ✕
            </button>

        </div>

    );

}