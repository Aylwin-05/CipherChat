import useMessages from "../../hooks/useMessages";

import ChatInput from "./ChatInput";
import MessageList from "./MessageList";

import "./Chat.css";

export default function ChatWindow({
    conversation,
    conversations,
    setConversations,
}) {

    // Always call hooks first
    const {
        messages,
        typingUsers,
        loading,
        sendMessage,
        typing,
        stopTyping,
    } = useMessages(
        conversation,
        (newMessage) => {

            if (!conversation) return;

            setConversations((previous) => {

                const updated = previous.map((conv) => {

                    if (conv.id !== conversation.id) {
                        return conv;
                    }

                    return {
                        ...conv,
                        updated_at: newMessage.created_at,
                        last_message: {
                            content: newMessage.content,
                            created_at: newMessage.created_at,
                        },
                    };

                });

                    updated.sort((a, b) => {

                        const dateA =
                            new Date(
                                a.updated_at ??
                                a.created_at ??
                                0
                            );

                        const dateB =
                            new Date(
                                b.updated_at ??
                                b.created_at ??
                                0
                            );

                        return dateB - dateA;

                    });

                return updated;

            });

        }
    );

    // Safe to return AFTER hooks
    if (!conversation) {

        return (

            <div className="chat-empty">

                <h2>Select a conversation</h2>

                <p>
                    Choose a conversation from the left.
                </p>

            </div>

        );

    }

    const otherUser =
        conversation.other_user ?? {
            display_name: "Unknown User",
            online_status: "offline",
        };

    return (

        <div className="chat-window">

            <div className="chat-header">

                <h3>
                    {otherUser.display_name}
                </h3>

                {typingUsers.length > 0 ? (

                    <span className="typing-indicator">
                        Typing...
                    </span>

                ) : (

                    <span className="online-status">

                        {otherUser.online_status === "online"
                            ? "🟢 Online"
                            : "⚫ Offline"}

                    </span>

                )}

            </div>

            <MessageList
                messages={messages}
                loading={loading}
            />

            <ChatInput
                onSend={sendMessage}
                typing={typing}
                stopTyping={stopTyping}
            />

        </div>

    );

}