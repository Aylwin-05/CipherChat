import { useEffect, useRef, useState } from "react";

import VoiceRecorder from "./VoiceRecorder";

import "./Chat.css";

import "./Chat.css";

function PaperclipIcon() {
    return (
        <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
        </svg>
    );
}

function SendIcon() {
    return (
        <svg
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="m22 2-7 20-4-9-9-4z" />
            <path d="M22 2 11 13" />
        </svg>
    );
}

export default function ChatInput({
    onSend,
    typing,
    stopTyping,
}) {

    const [text, setText] =
        useState("");

    const [selectedFile, setSelectedFile] =
        useState(null);

    const timeoutRef =
        useRef(null);

    const fileInputRef =
        useRef(null);

    // ==========================================================
    // Typing
    // ==========================================================

    function handleChange(e) {

        const value =
            e.target.value;

        setText(value);

        typing();

        clearTimeout(
            timeoutRef.current
        );

        timeoutRef.current =
            setTimeout(() => {

                stopTyping();

            }, 1000);

    }

    // ==========================================================
    // File Picker
    // ==========================================================

    function handleFileSelect(e) {

        const file =
            e.target.files[0];

        if (!file) return;

        setSelectedFile(file);

        e.target.value = "";

    }

    // ==========================================================
    // Voice Recorder Callback
    // ==========================================================

    function handleVoiceRecorded(file) {

        setSelectedFile(file);

    }

    // ==========================================================
    // Send
    // ==========================================================

    async function handleSend() {

        if (
            !text.trim() &&
            !selectedFile
        ) {
            return;
        }

        await onSend(

            text,

            selectedFile,

        );

        setText("");

        setSelectedFile(null);

        stopTyping();

    }

    // ==========================================================
    // Cleanup
    // ==========================================================

    useEffect(() => {

        return () => {

            clearTimeout(
                timeoutRef.current
            );

        };

    }, []);

    return (

        <div className="chat-input">

            <input

                ref={fileInputRef}

                type="file"

                style={{
                    display: "none",
                }}

                onChange={
                    handleFileSelect
                }

            />

            {selectedFile && (

                <div className="selected-file">

                    <svg
                        width="15"
                        height="15"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    >
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                    </svg>

                    <span className="selected-file-name">

                        {selectedFile.name}

                    </span>

                    <button

                        type="button"

                        className="selected-file-clear"

                        aria-label="Remove attachment"

                        onClick={() =>
                            setSelectedFile(null)
                        }

                    >

                        <svg
                            width="13"
                            height="13"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.4"
                            strokeLinecap="round"
                        >
                            <path d="M18 6 6 18M6 6l12 12" />
                        </svg>

                    </button>

                </div>

            )}

            <div className="chat-input-bar">

                {/* Voice Recorder */}

                <VoiceRecorder

                    onRecorded={
                        handleVoiceRecorded
                    }

                />

                {/* File Picker */}

                <button

                    type="button"

                    className="icon-btn"

                    aria-label="Attach file"

                    onClick={() =>
                        fileInputRef.current.click()
                    }

                >

                    <PaperclipIcon />

                </button>

                {/* Text */}

                <input

                    className="chat-input-field"

                    type="text"

                    value={text}

                    placeholder="Type a message..."

                    onChange={handleChange}

                    onKeyDown={(e) => {

                        if (
                            e.key === "Enter"
                        ) {

                            handleSend();

                        }

                    }}

                />

                {/* Send */}

                <button

                    type="button"

                    className="send-btn"

                    aria-label="Send message"

                    disabled={
                        !text.trim() && !selectedFile
                    }

                    onClick={handleSend}

                >

                    <SendIcon />

                </button>

            </div>

        </div>

    );

}