import { useEffect, useRef, useState } from "react";

import Sidebar from "../../components/layout/Sidebar";

import ConversationList from "../../components/chat/ConversationList";
import ChatWindow from "../../components/chat/ChatWindow";
import FriendsPage from "../../components/friends/FriendsPage";
import SettingsPage from "../Settings/SettingsPage";
import DeleteConversationModal from "../../components/chat/DeleteConversationModal";

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

    //------------------------------------------------------
    // Incoming two-party delete request: auto-open the
    // confirmation popup when someone wants to wipe a chat.
    // Each pending request prompts exactly once (keyed by
    // its id + timestamp) until it is resolved or replaced.
    //------------------------------------------------------

    const [pendingDeletePrompt, setPendingDeletePrompt] =
        useState(null);

    const promptSeenRef = useRef(null);

    useEffect(() => {

        if (!user) return;

        const incoming = conversations.find(conv =>

            conv.delete_requested_by &&
            conv.delete_requested_by !== user.id

        );

        if (!incoming) {

            setPendingDeletePrompt(null);

            return;

        }

        const key =
            `${incoming.id}:${incoming.delete_requested_at ?? ""}`;

        if (promptSeenRef.current === key) return;

        promptSeenRef.current = key;

        setPendingDeletePrompt(incoming);

    }, [conversations, user]);

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

    //----------------------------------------------------------
    // Group created: refresh the sidebar and open the chat
    //----------------------------------------------------------

    async function handleGroupCreated(group) {

        try {

            await refreshConversations();

            selectConversation(group.id);

        }
        catch (error) {

            console.error(
                "Unable to refresh after group creation",
                error
            );

        }

    }

    //----------------------------------------------------------
    // Left a group: drop it from the sidebar and close the chat
    //----------------------------------------------------------

    async function handleLeaveGroup() {

        try {

            await refreshConversations();

            selectConversation(null);

        }
        catch (error) {

            console.error(
                "Unable to refresh after leaving group",
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

                                    onGroupCreated={
                                        handleGroupCreated
                                    }

                                />

                            </div>

                            <div className="chat-panel">

                                <ChatWindow

                                    conversation={
                                        selectedConversation
                                    }

                                    onLeaveGroup={
                                        handleLeaveGroup
                                    }

                                />

                            </div>

                        </div>

                    )

            }

            {pendingDeletePrompt && (

                <DeleteConversationModal

                    conversation={
                        pendingDeletePrompt
                    }

                    onClose={() =>
                        setPendingDeletePrompt(null)
                    }

                />

            )}

        </div>

    );

}