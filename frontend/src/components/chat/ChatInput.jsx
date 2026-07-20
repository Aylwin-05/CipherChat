import { useState } from "react";

export default function ChatInput({
    onSend,
}) {

    const [
        text,
        setText,
    ] = useState("");

    async function handleSend() {

        if (!text.trim()) {
            return;
        }

        await onSend(text);

        setText("");
    }

    return (

        <div className="chat-input">

            <input
                type="text"
                placeholder="Type a message..."
                value={text}
                onChange={(e) =>
                    setText(e.target.value)
                }
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