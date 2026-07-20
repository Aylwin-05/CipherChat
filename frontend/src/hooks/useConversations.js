import { useEffect, useState } from "react";

import conversationService from "../services/conversationService";

export default function useConversations() {

    const [
        conversations,
        setConversations,
    ] = useState([]);

    const [
        loading,
        setLoading,
    ] = useState(true);

    const [
        error,
        setError,
    ] = useState(null);

    useEffect(() => {

        loadConversations();

    }, []);

    async function loadConversations() {

        try {

            setLoading(true);

            const data =
                await conversationService.getConversations();

            setConversations(data);

        } catch (err) {

            setError(err);

        } finally {

            setLoading(false);

        }

    }

    return {
        conversations,
        loading,
        error,
        refresh: loadConversations,
    };

}