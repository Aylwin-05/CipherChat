import { useAuth } from "../../context/AuthContext";

export default function MessageBubble({
    message,
}) {

    const { user } = useAuth();

    // Prevent rendering if message is missing
    if (!message) {
        return null;
    }

    // Safe comparison
    const isMine =
        String(user?.id) ===
        String(message?.sender_id);

    // Debug logs
    console.log("========== MESSAGE ==========");
    console.log("Current User:", user);
    console.log("Current User ID:", user?.id);
    console.log("Message:", message);
    console.log("Sender ID:", message?.sender_id);
    console.log("isMine:", isMine);
    console.log("=============================");

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
                    {message.content}
                </div>

                <div className="message-time">

                    {new Date(
                        message.created_at
                    ).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                    })}

                </div>

            </div>

        </div>

    );

}