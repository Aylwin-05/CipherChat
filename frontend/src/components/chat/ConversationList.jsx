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

            <div className="conv-list">

                <div className="conv-panel-header">

                    <h2 className="conv-title">Chats</h2>

                </div>

                <div className="conv-list-body">

                    {[0, 1, 2, 3, 4, 5].map((index) => (

                        <div key={index} className="conv-skeleton">

                            <div className="skeleton conv-skeleton-avatar" />

                            <div className="conv-skeleton-lines">

                                <div className="skeleton" style={{ height: 12, width: "55%" }} />

                                <div className="skeleton" style={{ height: 10, width: "80%" }} />

                            </div>

                        </div>

                    ))}

                </div>

            </div>

        );

    }

    return (

        <div className="conv-list">

            <div className="conv-panel-header">

                <h2 className="conv-title">Chats</h2>

                <span className="conv-count">

                    {conversations.length}

                </span>

            </div>

            <div className="conv-list-body">

                {

                    conversations.length === 0 && (

                        <div className="empty-state">

                            <div className="empty-icon">

                                <svg
                                    width="28"
                                    height="28"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="1.8"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                >
                                    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                                </svg>

                            </div>

                            <h3>No conversations yet</h3>

                            <p>
                                Open your Friends tab and
                                start chatting with someone.
                            </p>

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

        </div>

    );

}