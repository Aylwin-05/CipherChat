import { useEffect, useState } from "react";

import Sidebar from "../../components/layout/Sidebar";

import ConversationList from "../../components/chat/ConversationList";
import ChatWindow from "../../components/chat/ChatWindow";
import FriendsPage from "../../components/friends/FriendsPage";

import conversationService from "../../services/conversationService";

import { useAuth } from "../../context/AuthContext";

import "./Dashboard.css";

export default function Dashboard() {

    const { user } = useAuth();

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

        catch (error) {

            console.error(error);

        }

        finally {

            setLoading(false);

        }

    }

    //----------------------------------------------------------
    // Select conversation (clears its unread badge)
    //----------------------------------------------------------

    function handleSelectConversation(conversation) {

        setSelectedConversation(conversation);

        if (
            conversation.unread_count > 0 ||
            conversation.other_user
        ) {

            setConversations(previous =>

                previous.map(item =>

                    item.id === conversation.id

                        ? {

                            ...item,

                            unread_count: 0,

                        }
                        : item

                )

            );

        }

    }

    //----------------------------------------------------------
    // Start Chat
    //----------------------------------------------------------

    async function handleStartChat(friend) {

        try {

            //--------------------------------------------------
            // Find the other user
            //--------------------------------------------------

            const targetUser =

                friend.sender.id === user.id

                    ? friend.receiver

                    : friend.sender;

            //--------------------------------------------------
            // Create/Open conversation
            //--------------------------------------------------

            const openedConversation =

                await conversationService.createPrivateConversation(

                    targetUser.id

                );

            //--------------------------------------------------
            // Reload conversations
            //--------------------------------------------------

            const updatedConversations =

                await conversationService.getConversations();

            setConversations(
                updatedConversations
            );

            //--------------------------------------------------
            // Select opened conversation
            //--------------------------------------------------

            const selected =

                updatedConversations.find(

                    conversation =>

                        conversation.id ===
                        openedConversation.id

                );

            if (selected) {

                setSelectedConversation(
                    selected
                );

            }

            //--------------------------------------------------
            // Switch to Chats
            //--------------------------------------------------

            setCurrentPage("chats");

        }

        catch (error) {

            console.error(
                "Unable to open conversation",
                error
            );

        }

    }

    return (

        <div className="app-shell">

            <Sidebar

                currentPage={currentPage}

                setCurrentPage={setCurrentPage}

            />

            {

                currentPage === "friends"

                    ? (

                        <div className="app-stage friends-stage">

                            <FriendsPage

                                onStartChat={
                                    handleStartChat
                                }

                            />

                        </div>

                    )

                    : (

                        <div className="app-stage">

                            <div className="conv-panel">

                                <ConversationList

                                    conversations={
                                        conversations
                                    }

                                    loading={
                                        loading
                                    }

                                    selectedConversation={
                                        selectedConversation
                                    }

                                    onSelectConversation={
                                        handleSelectConversation
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

    );

}