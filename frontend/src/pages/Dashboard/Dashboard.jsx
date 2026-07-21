import { useEffect, useState } from "react";

import Sidebar from "../../components/layout/Sidebar";

import ConversationList from "../../components/chat/ConversationList";
import ChatWindow from "../../components/chat/ChatWindow";

import conversationService from "../../services/conversationService";

import "./Dashboard.css";

export default function Dashboard() {

    const [
        conversations,
        setConversations,
    ] = useState([]);

    const [
        loading,
        setLoading,
    ] = useState(true);

    const [
        selectedConversation,
        setSelectedConversation,
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

            if (
                data.length > 0 &&
                !selectedConversation
            ) {

                setSelectedConversation(
                    data[0]
                );

            }

        } finally {

            setLoading(false);

        }

    }

    return (

        <div className="dashboard">

            <Sidebar />

            <div className="dashboard-main">

                <header className="dashboard-header">

                    <h2>

                        CipherChat

                    </h2>

                </header>

                <div className="dashboard-content">

                    <div className="conversation-panel">

                        <h3>

                            Conversations

                        </h3>

                        <ConversationList

                            conversations={conversations}

                            loading={loading}

                            selectedConversation={
                                selectedConversation
                            }

                            onSelectConversation={
                                setSelectedConversation
                            }

                        />

                    </div>

                    <div className="chat-panel">

                        <ChatWindow

                            conversation={
                                selectedConversation
                            }

                            conversations={
                                conversations
                            }

                            setConversations={
                                setConversations
                            }

                        />

                    </div>

                </div>

            </div>

        </div>

    );

}