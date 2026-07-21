import { useEffect, useState } from "react";

import { useAuth } from "../context/AuthContext";

import messageService from "../services/messageService";
import websocketService from "../services/websocketService";

export default function useMessages(
    conversationId,
    onNewMessage,
) {

    const { user } = useAuth();

    const [messages, setMessages] =
        useState([]);

    const [typingUsers, setTypingUsers] =
        useState([]);

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState(null);

    useEffect(() => {

        if (!conversationId) {

            setMessages([]);

            websocketService.disconnect();

            return;

        }

        initialize();

        return () => {

            websocketService.disconnect();

        };

    }, [conversationId]);

    async function initialize() {

        try {

            setLoading(true);

            const history =
                await messageService.getMessages(
                    conversationId
                );

            setMessages(history);

            const token =
                localStorage.getItem(
                    "access_token"
                );

            websocketService.connect(
                conversationId,
                token
            );

            websocketService.onMessage(
                (event) => {

                    switch (event.event) {

                        case "connected":

                            break;

                        case "message":

                            setMessages((previous) => {

                                const exists =
                                    previous.some(
                                        (msg) =>
                                            msg.id ===
                                            event.id
                                    );

                                if (exists) {
                                    return previous;
                                }

                                return [
                                    ...previous,
                                    event,
                                ];

                            });

                            if (onNewMessage) {

                                onNewMessage(event);

                            }

                            break;

                        case "typing":

                            if (
                                event.user_id !==
                                user?.id
                            ) {

                                setTypingUsers(
                                    (previous) => {

                                        if (
                                            previous.includes(
                                                event.user_id
                                            )
                                        ) {

                                            return previous;

                                        }

                                        return [
                                            ...previous,
                                            event.user_id,
                                        ];

                                    }
                                );

                            }

                            break;

                        case "stop_typing":

                            setTypingUsers(
                                (previous) =>
                                    previous.filter(
                                        (id) =>
                                            id !==
                                            event.user_id
                                    )
                            );

                            break;

                        case "error":

                            console.error(
                                event.message
                            );

                            break;

                        default:

                            break;

                    }

                }
            );

        } catch (err) {

            setError(err);

        } finally {

            setLoading(false);

        }

    }

    function sendMessage(content) {

        websocketService.sendMessage(
            content
        );

    }

    function typing() {

        websocketService.sendTyping();

    }

    function stopTyping() {

        websocketService.stopTyping();

    }

    return {

        messages,

        typingUsers,

        loading,

        error,

        sendMessage,

        typing,

        stopTyping,

    };

}