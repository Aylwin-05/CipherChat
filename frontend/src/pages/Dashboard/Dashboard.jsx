import { useEffect, useState } from "react";

import Sidebar from "../../components/layout/Sidebar";

import ConversationList from "../../components/chat/ConversationList";
import ChatWindow from "../../components/chat/ChatWindow";
import FriendsPage from "../../components/friends/FriendsPage";

import conversationService from "../../services/conversationService";

import "./Dashboard.css";

export default function Dashboard() {

    const [
        currentPage,
        setCurrentPage,
    ] = useState("chats");

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

        }

        finally {

            setLoading(false);

        }

    }

    //----------------------------------------------------------
    // Start chat from Friends page
    //----------------------------------------------------------

    async function handleStartChat(friend) {

        try {

            /*
                For now we'll simply switch back
                to Chats.

                In the next step we'll make this:

                - Find existing conversation
                - OR create one automatically
                - Then open it
            */

            setCurrentPage("chats");

        }

        catch (error) {

            console.error(error);

        }

    }

    return (

        <div className="dashboard">

            <Sidebar

                currentPage={currentPage}

                setCurrentPage={setCurrentPage}

            />

            <div className="dashboard-main">

                <header className="dashboard-header">

                    <h2>

                        CipherChat

                    </h2>

                </header>

                {

                    currentPage === "friends"

                    ?

                    (

                        <FriendsPage

                            onStartChat={
                                handleStartChat
                            }

                        />

                    )

                    :

                    (

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

                    )

                }

            </div>

        </div>

    );

}