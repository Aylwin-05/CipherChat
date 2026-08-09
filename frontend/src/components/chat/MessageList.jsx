import { useEffect, useRef } from "react";

import MessageBubble from "./MessageBubble";

export default function MessageList({
    messages,
    loading,
    onDelete,
}) {

    const bottomRef = useRef(null);

    useEffect(() => {

        bottomRef.current?.scrollIntoView({
            behavior: "smooth",
        });

    }, [messages]);

    if (loading) {

        return (

            <div className="chat-loading-list">

                {[0, 1, 2].map((index) => (

                    <div
                        key={index}
                        className={
                            index % 2 === 0
                                ? "chat-loading-bubble alt"
                                : "chat-loading-bubble"
                        }
                    >

                        <div className="skeleton" style={{
                            width: "100%",
                            height: 46,
                            borderRadius: 18,
                        }} />

                    </div>

                ))}

            </div>

        );

    }

    if (messages.length === 0) {

        return (

            <div className="message-list">

                <div className="empty-state">

                    <div className="empty-icon">

                        <svg
                            width="26"
                            height="26"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                        </svg>

                    </div>

                    <h3>No messages yet</h3>

                    <p>
                        Send the first secure message
                        to start the conversation.
                    </p>

                </div>

            </div>

        );

    }

    return (

        <div className="message-list">

            {

                messages.map((message) => (

                    <MessageBubble
                        key={message.id}
                        message={message}
                        onDelete={onDelete}
                    />

                ))

            }

            <div ref={bottomRef} />

        </div>

    );

}