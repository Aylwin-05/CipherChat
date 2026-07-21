import { useEffect, useRef, useState } from "react";

export default function ChatInput({
    onSend,
    typing,
    stopTyping,
}) {

    const [text, setText] = useState("");

    const timeoutRef = useRef(null);

    function handleChange(e) {

        const value = e.target.value;

        setText(value);

        typing();

        clearTimeout(timeoutRef.current);

        timeoutRef.current = setTimeout(() => {

            stopTyping();

        }, 1000);

    }

    function handleSend() {

        if (!text.trim()) {
            return;
        }

        onSend(text);

        setText("");

        stopTyping();
    }

    useEffect(() => {

        return () => {

            clearTimeout(timeoutRef.current);

        };

    }, []);

    return (

        <div className="chat-input">

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

    );

}