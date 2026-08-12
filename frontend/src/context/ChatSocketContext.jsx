import {
    createContext,
    useContext,
    useEffect,
    useRef,
    useState,
} from "react";

import { useAuth } from "./AuthContext";

import conversationService from "../services/conversationService";
import websocketService from "../services/websocketService";

import {
    getAccessToken,
} from "../api/api";

const ChatSocketContext = createContext(null);

export function ChatSocketProvider({ children }) {

    const { user } = useAuth();

    const [conversations, setConversations] =
        useState([]);

    const [presence, setPresence] =
        useState({});

    const [activeConversationId, setActiveConversationId] =
        useState(null);

    const [loading, setLoading] =
        useState(true);

    const listenersRef = useRef(new Set());

    const activeRef = useRef(null);

    const userRef = useRef(user);

    useEffect(() => {

        userRef.current = user;

    }, [user]);

    useEffect(() => {

        activeRef.current = activeConversationId;

    }, [activeConversationId]);

    //=====================================================
    // Fan-out: subscribers (e.g. useMessages) receive every
    // raw event; the provider itself keeps global state.
    //=====================================================

    function emit(event) {

        listenersRef.current.forEach(
            listener => listener(event)
        );

    }

    //=====================================================
    // Conversations: initial fetch + catch-up after every
    // (re)connect so no offline event is ever missed.
    //=====================================================

    async function loadConversations() {

        try {

            setLoading(true);

            const data =
                await conversationService.getConversations();

            setConversations(data);

            if (
                data.length > 0 &&
                !activeRef.current
            ) {

                // Never auto-open an archived conversation.
                const firstActive =
                    data.find(c => !c.is_archived);

                if (firstActive) {

                    setActiveConversationId(
                        firstActive.id
                    );

                }

            }

        }

        catch (error) {

            console.error(error);

        }

        finally {

            setLoading(false);

        }

    }

    //=====================================================
    // Socket lifecycle: ONE user-scoped connection keeps
    // the whole UI (sidebar included) live.
    //=====================================================

    useEffect(() => {

        if (!user) return;

        websocketService.connect(
            getAccessToken()
        );

        websocketService.onMessage(
            async (event) => {

                switch (event.event) {

                    case "connected":

                        await loadConversations();

                        break;

                    case "presence":

                        if (
                            event.user_id &&
                            event.user_id !== userRef.current?.id
                        ) {

                            setPresence(previous => ({

                                ...previous,

                                [event.user_id]:
                                    event.online,

                            }));

                        }

                        break;

                    case "message": {

                        const conversationId =
                            event.conversation_id;

                        if (
                            conversationId &&
                            event.sender_id !==
                                userRef.current?.id
                        ) {

                            if (
                                conversationId !==
                                activeRef.current
                            ) {

                                // Background conversation:
                                // bump its unread pill and
                                // acknowledge delivery.
                                setConversations(
                                    previous =>
                                        previous.map(
                                            conversation =>

                                                conversation.id ===
                                                conversationId

                                                    ? {

                                                        ...conversation,

                                                        unread_count:
                                                            (conversation.unread_count ?? 0) + 1,

                                                    }

                                                    : conversation
                                        )
                                );

                                websocketService.sendDelivered(
                                    conversationId,
                                    event.id,
                                );

                            }

                        }

                        break;

                    }

                }

                emit(event);

            }
        );

        return () => {

            websocketService.disconnect();

        };

    }, [user]);

    //=====================================================
    // Select a conversation: live UI state + reset unread
    //=====================================================

    function selectConversation(conversationId) {

        setActiveConversationId(conversationId);

        setConversations(previous =>

            previous.map(item =>

                item.id === conversationId

                    ? {

                        ...item,

                        unread_count: 0,

                    }

                    : item

            )

        );

    }

    //=====================================================
    // Bump a conversation to the top with the latest
    // message (plaintext when known; null = 'Encrypted
    // message' preview for background conversations).
    //=====================================================

    function bumpConversation(
        conversationId,
        message,
        targetConversation,
    ) {

        if (!conversationId) return;

        setConversations((previous) => {

            const existing =
                previous.some(
                    conv => conv.id === conversationId
                );

            const base = existing
                ? previous
                : [
                    ...previous,
                    targetConversation,
                ].filter(Boolean);

            const updated = base.map((conv) => {

                if (conv.id !== conversationId) {

                    return conv;

                }

                return {
                    ...conv,
                    updated_at: message.created_at,
                    last_message: {
                        content: message.content,
                        created_at: message.created_at,
                    },
                };

            });

            // Pinned chats stay on top; recency within each group
            updated.sort((a, b) => {

                const pinnedA = a.is_pinned ? 0 : 1;

                const pinnedB = b.is_pinned ? 0 : 1;

                if (pinnedA !== pinnedB) {
                    return pinnedA - pinnedB;
                }

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

    //=====================================================
    // Update conversation settings (pin / archive / mute)
    //=====================================================

    async function updateSettings(
        conversationId,
        settings,
    ) {

        const updated =
            await conversationService.updateSettings(
                conversationId,
                settings,
            );

        setConversations(previous => {

            const updatedList = previous.map((conv) => {

                if (conv.id === conversationId) {

                    return {
                        ...conv,
                        is_pinned:
                            updated.is_pinned ??
                            conv.is_pinned,
                        is_archived:
                            updated.is_archived ??
                            conv.is_archived,
                        muted:
                            updated.muted ??
                            conv.muted,
                        disappear_after_seconds:
                            "disappear_after_seconds" in updated
                                ? updated.disappear_after_seconds
                                : conv.disappear_after_seconds,
                    };

                }

                return conv;

            });

            // Re-apply pinned-first ordering locally so the UI
            // reacts instantly without a server round-trip.
            const pinned = updatedList.filter(c => c.is_pinned);

            const rest = updatedList.filter(c => !c.is_pinned);

            return [
                ...pinned,
                ...rest,
            ];

        });

        return updated;

    }

    //=====================================================
    // Raw event subscription for per-conversation hooks
    //=====================================================

    function subscribe(listener) {

        listenersRef.current.add(listener);

        return () => {

            listenersRef.current.delete(listener);

        };

    }

    const value = {

        conversations,

        presence,

        loading,

        activeConversationId,

        selectConversation,

        bumpConversation,

        updateSettings,

        subscribe,

        refreshConversations: loadConversations,

    };

    return (

        <ChatSocketContext.Provider value={value}>

            {children}

        </ChatSocketContext.Provider>

    );

}

export function useChatSocket() {

    return useContext(ChatSocketContext);

}