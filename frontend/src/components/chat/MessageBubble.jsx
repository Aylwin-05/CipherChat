import { useAuth } from "../../context/AuthContext";

export default function MessageBubble({
    message,
}) {

    const { user } = useAuth();

    if (!message) {
        return null;
    }

    const isMine =
        String(user?.id) ===
        String(message?.sender_id);

    const content =
        message.deleted_for_everyone
            ? "🚫 Message deleted"
            : message.content;

    return (

        <div
            className={`message-row ${
                isMine ? "mine" : "other"
            }`}
        >

            <div
                className={`message-bubble ${
                    isMine ? "mine" : "other"
                }`}
            >

                <div className="message-content">

                    {content}

                </div>

                <div className="message-footer">

                    <span className="message-time">

                        {new Date(
                            message.created_at
                        ).toLocaleTimeString([], {

                            hour: "2-digit",

                            minute: "2-digit",

                        })}

                    </span>

                    {

                        message.edited && (

                            <span className="message-edited">

                                Edited

                            </span>

                        )

                    }

                    {

                        isMine && (

                            <span className="message-status">

                                {

                                    message.is_read

                                        ? "✓✓"

                                        : message.delivered_at

                                            ? "✓✓"

                                            : "✓"

                                }

                            </span>

                        )

                    }

                </div>

            </div>

        </div>

    );

}