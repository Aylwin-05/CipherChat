import {
    useEffect,
    useRef,
} from "react";

import MessageBubble from "./MessageBubble";

import { useAuth } from "../../context/AuthContext";

const PIN_THRESHOLD = 80;

export default function MessageList({
    messages,
    loading,
    onDelete,
    conversationId,
}) {

    const { user } = useAuth();

    const containerRef = useRef(null);

    const contentRef = useRef(null);

    const pinnedRef = useRef(true);

    const prevConversationRef = useRef(null);

    // ==========================================================
    // Chronological order: oldest at the top, newest at the
    // bottom (WhatsApp layout). Scrolling up reads history.
    // ==========================================================

    // ==========================================================
    // A new conversation (or the first one) starts pinned to
    // the bottom so the latest message is always visible.
    // ==========================================================

    useEffect(() => {

        if (conversationId !== prevConversationRef.current) {

            prevConversationRef.current = conversationId;

            pinnedRef.current = true;

        }

    }, [conversationId]);

    // ==========================================================
    // Keep track of whether the user is reading at the newest
    // end (bottom). Scrolling up unpins; returning to the
    // bottom re-pins.
    // ==========================================================

    function handleScroll() {

        const container = containerRef.current;

        if (!container) return;

        const distanceFromBottom =
            container.scrollHeight -
            container.scrollTop -
            container.clientHeight;

        pinnedRef.current =
            distanceFromBottom < PIN_THRESHOLD;

    }

    // ==========================================================
    // After the message list changes — or when it finishes
    // loading (the list only appears once `loading` flips to
    // false, and that flip can land in a different render than
    // the messages update) — jump to the newest message if we
    // are pinned there, or if we just sent a message. When the
    // user is reading history, do NOT yank them away.
    // ==========================================================

    useEffect(() => {

        if (loading) return;

        const container = containerRef.current;

        if (!container) return;

        const lastMessage =
            messages[messages.length - 1];

        const isOwn =
            lastMessage &&
            lastMessage.sender_id === user?.id;

        if (pinnedRef.current || isOwn) {

            container.scrollTop =
                container.scrollHeight;

            // A second pass after layout settles (fonts,
            // async content) so the newest message is
            // actually on screen when opening a chat.
            requestAnimationFrame(() => {

                if (
                    container &&
                    pinnedRef.current
                ) {

                    container.scrollTop =
                        container.scrollHeight;

                }

            });

        }

    }, [messages, loading, conversationId, user?.id]);

    // ==========================================================
    // Content size changes (images finishing loading, voice
    // notes, etc.) shift the layout. Stay glued to the newest
    // message as long as the user is pinned at the bottom.
    //
    // Re-attached whenever the list is (re)mounted, because
    // the skeleton replaces the list while loading and the
    // content node is recreated each time.
    // ==========================================================

    useEffect(() => {

        if (loading) return;

        const container = containerRef.current;

        const content = contentRef.current;

        if (!container || !content) return;

        const observer = new ResizeObserver(() => {

            if (pinnedRef.current) {

                container.scrollTop =
                    container.scrollHeight;

            }

        });

        observer.observe(content);

        return () => observer.disconnect();

    }, [loading, conversationId]);

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

        <div
            className="message-list"
            ref={containerRef}
            onScroll={handleScroll}
        >

            <div className="message-list-inner" ref={contentRef}>

                {

                    messages.map((message) => (

                        <MessageBubble
                            key={message.id}
                            message={message}
                            onDelete={onDelete}
                        />

                    ))

                }

            </div>

        </div>

    );

}
