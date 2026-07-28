import { useEffect, useRef, useState } from "react";

export default function ChatInput({
    onSend,
    typing,
    stopTyping,
}) {

    const [text, setText] = useState("");

    const [selectedFile, setSelectedFile] =
        useState(null);

    const timeoutRef = useRef(null);

    const fileInputRef = useRef(null);

    // ==========================================================
    // Typing
    // ==========================================================

    function handleChange(e) {

        const value = e.target.value;

        setText(value);

        typing();

        clearTimeout(timeoutRef.current);

        timeoutRef.current = setTimeout(() => {

            stopTyping();

        }, 1000);

    }

    // ==========================================================
    // File Select
    // ==========================================================

    function handleFileSelect(e) {

        const file = e.target.files[0];

        if (!file) return;

        setSelectedFile(file);

        e.target.value = "";

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

            clearTimeout(timeoutRef.current);

        };

    }, []);

    return (

        <div className="chat-input">

            <input
                ref={fileInputRef}
                type="file"
                style={{ display: "none" }}
                onChange={handleFileSelect}
            />

            {selectedFile && (

                <div
                    className="selected-file"
                >

                    <span>
                        📎 {selectedFile.name}
                    </span>

                    <button
                        onClick={() =>
                            setSelectedFile(null)
                        }
                    >
                        ✕
                    </button>

                </div>

            )}

            <div className="chat-input-row">

                <button
                    type="button"
                    onClick={() =>
                        fileInputRef.current.click()
                    }
                >
                    📎
                </button>

                <input
                    type="text"
                    value={text}
                    placeholder="Type a message..."
                    onChange={handleChange}
                    onKeyDown={(e) => {

                        if (e.key === "Enter") {

                            handleSend();

                        }

                    }}
                />

                <button
                    onClick={handleSend}
                >
                    Send
                </button>

            </div>

        </div>

    );

}