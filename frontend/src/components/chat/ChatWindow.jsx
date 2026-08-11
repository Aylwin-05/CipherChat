import { useState } from "react";

import useMessages from "../../hooks/useMessages";

import ChatInput from "./ChatInput";
import MessageList from "./MessageList";
import ForwardModal from "./ForwardModal";

import UserAvatar from "../UserAvatar";
import { useAuth } from "../../context/AuthContext";
import { useChatSocket } from "../../context/ChatSocketContext";

import "./Chat.css";

export default function ChatWindow({
    conversation,
}) {

    const { user } = useAuth();

    const {
        presence,
        bumpConversation,
    } = useChatSocket();

    // Always call hooks first
    const {
        messages,
        typingUsers,
        loading,
        error,
        sendMessage,
        editMessage,
        toggleReaction,
        forwardMessage,
        deleteMessage,
        typing,
        stopTyping,
    } = useMessages(
        conversation,
        (newMessage) => {

            if (!conversation) return;

            bumpConversation(
                conversation.id,
                newMessage,
            );

        }
    );

    // ==========================================================
    // Bump a conversation to the top with the latest message
    // (delegated to the ChatSocket provider, which owns the
    // sidebar list)
    // ==========================================================

    // ==========================================================
    // Reply / edit / forward / reactions state
    // ==========================================================

    const [replyTo, setReplyTo] =
        useState(null);

    const [editTarget, setEditTarget] =
        useState(null);

    const [forwardTarget, setForwardTarget] =
        useState(null);

    function handleReply(message) {

        setReplyTo({

            ...message,

            sender_display_name:
                message.sender_id === user?.id
                    ? user?.display_name
                    : otherUser.display_name,

        });

    }

    function handleEdit(message) {

        setReplyTo(null);

        setEditTarget(message);

    }

    function handleCancelEdit() {

        setEditTarget(null);

    }

    async function handleEditSubmit(messageId, text) {

        await editMessage(messageId, text);

        setEditTarget(null);

    }

    async function handleSend(text, file) {

        await sendMessage(
            text,
            file,
            {
                replyToId: replyTo?.id,
            },
        );

        setReplyTo(null);

    }

    async function handleForwardSubmit(plaintext, recipients) {

        const results =
            await forwardMessage(
                plaintext,
                recipients,
            );

        // Surface forwarded copies in the sidebar
        for (const result of results) {

            bumpConversation(
                result.conversation.id,
                {
                    content: plaintext,
                    created_at:
                        result.message.created_at,
                },
                result.conversation,
            );

        }

    }

    // Safe to return AFTER hooks
    if (!conversation) {

        return (

            <div className="chat-empty">

                <div className="chat-empty-logo">

                    <svg
                        width="56"
                        height="56"
                        viewBox="0 0 32 32"
                        fill="none"
                    >
                        <defs>
                            <linearGradient
                                id="emptyGrad"
                                x1="0"
                                y1="0"
                                x2="1"
                                y2="1"
                            >
                                <stop offset="0" stopColor="#7c5cff" />
                                <stop offset="1" stopColor="#22d3ee" />
                            </linearGradient>
                        </defs>
                        <path
                            d="M16 2l12 4v8c0 8-5 14-12 16C9 28 4 22 4 14V6z"
                            fill="url(#emptyGrad)"
                        />
                    </svg>

                </div>

                <h2>Select a conversation</h2>

                <p>
                    Your messages are encrypted end-to-end.
                    Pick a chat to start talking.
                </p>

            </div>

        );

    }

    const otherUser =
        conversation.other_user ?? {
            display_name: "Unknown User",
            online_status: "offline",
        };

    const liveOnline =
        presence[otherUser.id] ??
        otherUser.online_status === "online";

    // Friendly wording for common errors
    const errorMessage = error
        ? /no (registered )?devic|no-such-device|bundle unavailable/i.test(
            error.message ?? "",
        )
            ? `${otherUser.display_name} hasn't set up
               end-to-end encryption yet. Ask them to
               log in once so their secure device is ready.`
            : error.message
        : null;

    return (

        <div className="chat-window">

            <div className="chat-header">

                <div className="chat-identity">

                    <UserAvatar
                        user={otherUser}
                        className="chat-avatar"
                    >
                        <span
                            className={`chat-presence ${
                                liveOnline ? "online" : ""
                            }`}
                        />
                    </UserAvatar>

                    <div className="chat-heading">

                        <h3 className="chat-name">

                            {otherUser.display_name}

                        </h3>

                        {typingUsers.length > 0 ? (

                            <div className="chat-status typing">

                                <span className="typing-dots">

                                    <span />
                                    <span />
                                    <span />

                                </span>

                                Typing…

                            </div>

                        ) : (

                            <div className="chat-status">

                                {liveOnline
                                    ? "Online"
                                    : "Offline"}

                            </div>

                        )}

                    </div>

                </div>

                <div className="chat-header-actions">

                    <span className="e2e-chip" title="Signal protocol, end-to-end encrypted">

                        <svg
                            width="13"
                            height="13"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <rect x="3" y="11" width="18" height="11" rx="2" />
                            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                        </svg>

                        E2E

                    </span>

                </div>

            </div>

            <MessageList
                messages={messages}
                loading={loading}
                onDelete={deleteMessage}
                onReply={handleReply}
                onEdit={handleEdit}
                onForward={setForwardTarget}
                onToggleReaction={toggleReaction}
                otherUser={otherUser}
                conversationId={conversation.id}
            />

            {errorMessage ? (

                <div className="chat-error-banner">

                    <svg
                        width="16"
                        height="16"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                    >
                        <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                        <path d="M12 9v4M12 17h.01" />
                    </svg>

                    {errorMessage}

                </div>

            ) : null}

            <ChatInput
                onSend={handleSend}
                typing={typing}
                stopTyping={stopTyping}
                replyTo={replyTo}
                onCancelReply={() =>
                    setReplyTo(null)
                }
                editTarget={editTarget}
                onEdit={handleEditSubmit}
                onCancelEdit={handleCancelEdit}
            />

            {forwardTarget && (

                <ForwardModal
                    message={forwardTarget}
                    excludeUserId={otherUser.id}
                    onClose={() =>
                        setForwardTarget(null)
                    }
                    onForward={handleForwardSubmit}
                />

            )}

        </div>

    );

}
