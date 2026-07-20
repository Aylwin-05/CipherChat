import { useEffect, useRef } from "react";

import MessageBubble from "./MessageBubble";

export default function MessageList({
    messages,
    loading,
}) {

    const bottomRef = useRef(null);

    useEffect(() => {

        bottomRef.current?.scrollIntoView({
            behavior: "smooth",
        });

    }, [messages]);

    if (loading) {

        return (
            <div className="message-list">

                Loading messages...

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
                    />

                ))

            }

            <div ref={bottomRef} />

        </div>

    );

}