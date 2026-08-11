import { useState } from "react";

import Sidebar from "../../components/layout/Sidebar";

import ConversationList from "../../components/chat/ConversationList";
import ChatWindow from "../../components/chat/ChatWindow";
import FriendsPage from "../../components/friends/FriendsPage";
import SettingsPage from "../Settings/SettingsPage";

import conversationService from "../../services/conversationService";

import { useAuth } from "../../context/AuthContext";
import {
    ChatSocketProvider,
    useChatSocket,
} from "../../context/ChatSocketContext";

import "./Dashboard.css";

export default function Dashboard() {

    return (

        <ChatSocketProvider>

            <DashboardInner />

        </ChatSocketProvider>

    );

}

function DashboardInner() {

    const { user } = useAuth();

    const {
        conversations,
        loading,
        activeConversationId,
        selectConversation,
        refreshConversations,
    } = useChatSocket();

    const [
        currentPage,
        setCurrentPage,
    ] = useState("chats");

    const selectedConversation =
        conversations.find(
            conversation =>
                conversation.id ===
                activeConversationId
        ) ?? null;

    //----------------------------------------------------------
    // Select conversation (clears its unread badge)
    //----------------------------------------------------------

    function handleSelectConversation(conversation) {

        selectConversation(conversation.id);

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

            await refreshConversations();

            //--------------------------------------------------
            // Select opened conversation
            //--------------------------------------------------

            selectConversation(
                openedConversation.id
            );

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

                    : currentPage === "settings"

                        ? (

                            <div className="app-stage settings-stage">

                                <SettingsPage />

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

                                />

                            </div>

                        </div>

                    )

            }

        </div>

    );

}