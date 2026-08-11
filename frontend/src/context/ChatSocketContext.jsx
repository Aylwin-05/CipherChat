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

                setActiveConversationId(
                    data[0].id
                );

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