import useMessages from "../../hooks/useMessages";

import MessageList from "./MessageList";
import ChatInput from "./ChatInput";

import "./Chat.css";

export default function ChatWindow({
    conversation,
}) {
    if (!conversation) {
        return (
            <div className="chat-empty">
                <h2>Select a conversation</h2>
                <p>
                    Choose a conversation from the left to
                    start chatting.
                </p>
            </div>
        );
    }

    const {
        messages,
        loading,
        sendMessage,
    } = useMessages(conversation.id);

    return (
        <div className="chat-window">

            <div className="chat-header">

                <h3>
                    Conversation
                </h3>

                <span>
                    {conversation.id}
                </span>

            </div>

            <MessageList
                messages={messages}
                loading={loading}
            />

            <ChatInput
                onSend={sendMessage}
            />

        </div>
    );
}