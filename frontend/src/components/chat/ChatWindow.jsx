import useMessages from "../../hooks/useMessages";

import ChatInput from "./ChatInput";
import MessageList from "./MessageList";

import "./Chat.css";

export default function ChatWindow({

    conversation,

    conversations,

    setConversations,

}) {

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

    const {

        messages,

        typingUsers,

        loading,

        sendMessage,

        typing,

        stopTyping,

    } = useMessages(

        conversation.id,

        (newMessage) => {

            setConversations((previous) => {

                const updated = previous.map((conv) => {

                    if (
                        conv.id !==
                        conversation.id
                    ) {

                        return conv;

                    }

                    return {

                        ...conv,

                        updated_at:
                            newMessage.created_at,

                        last_message: {

                            content:
                                newMessage.content,

                            created_at:
                                newMessage.created_at,

                        },

                    };

                });

                updated.sort(

                    (a, b) =>

                        new Date(
                            b.updated_at
                        ) -

                        new Date(
                            a.updated_at
                        )

                );

                return updated;

            });

        }

    );

    const otherUser =
        conversation.other_user;

    return (

        <div className="chat-window">

            <div className="chat-header">

                <h3>

                    {otherUser.display_name}

                </h3>

                {

                    typingUsers.length > 0

                        ? (

                            <span className="typing-indicator">

                                Typing...

                            </span>

                        )

                        : (

                            <span className="online-status">

                                {

                                    otherUser.online_status ===
                                    "online"

                                        ? "🟢 Online"

                                        : "⚫ Offline"

                                }

                            </span>

                        )

                }

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