import { useEffect, useState } from "react";

import messageService from "../services/messageService";

export default function useMessages(
    conversationId,
) {
    const [
        messages,
        setMessages,
    ] = useState([]);

    const [
        loading,
        setLoading,
    ] = useState(false);

    const [
        error,
        setError,
    ] = useState(null);

    useEffect(() => {

        if (!conversationId) {
            setMessages([]);
            return;
        }

        loadMessages();

    }, [conversationId]);

    async function loadMessages() {

        try {

            setLoading(true);

            const data =
                await messageService.getMessages(
                    conversationId,
                );

            setMessages(data);

        } catch (err) {

            setError(err);

        } finally {

            setLoading(false);

        }

    }

    async function sendMessage(
        content,
    ) {

        const message =
            await messageService.sendMessage(
                conversationId,
                content,
            );

        setMessages((previous) => [
            ...previous,
            message,
        ]);

        return message;

    }

    return {
        messages,
        loading,
        error,
        sendMessage,
        refresh: loadMessages,
    };
}