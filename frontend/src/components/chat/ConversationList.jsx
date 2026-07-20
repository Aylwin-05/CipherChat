import { useState } from "react";

import useConversations from "../../hooks/useConversations";

import ConversationItem from "./ConversationItem";

import "./ConversationList.css";

export default function ConversationList() {

    const {

        conversations,

        loading,

    } = useConversations();

    const [

        selectedConversation,

        setSelectedConversation,

    ] = useState(null);

    if (loading) {

        return (

            <div className="conversation-list">

                Loading conversations...

            </div>

        );

    }

    return (

        <div className="conversation-list">

            {

                conversations.length === 0 && (

                    <div className="empty">

                        No conversations

                    </div>

                )

            }

            {

                conversations.map(

                    (conversation) => (

                        <ConversationItem

                            key={conversation.id}

                            conversation={conversation}

                            selected={
                                selectedConversation?.id ===
                                conversation.id
                            }

                            onSelect={
                                setSelectedConversation
                            }

                        />

                    )

                )

            }

        </div>

    );

}