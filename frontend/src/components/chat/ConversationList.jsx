import "./ConversationList.css";

import ConversationItem from "./ConversationItem";

export default function ConversationList({

    conversations,

    loading,

    selectedConversation,

    onSelectConversation,

}) {

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
                                onSelectConversation
                            }

                        />

                    )

                )

            }

        </div>

    );

}