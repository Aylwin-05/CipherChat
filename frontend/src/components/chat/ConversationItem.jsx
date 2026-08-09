import "./ConversationList.css";

export default function ConversationItem({

    conversation,
    selected,
    onSelect,

}) {

    const user = conversation.other_user;

    const unread =
        !selected
            ? (conversation.unread_count ?? 0)
            : 0;

    return (

        <div
            className={
                selected
                    ? "conversation-item active"
                    : "conversation-item"
            }
            onClick={() => onSelect(conversation)}
        >

            <div className="conversation-avatar">

                {
                    user.display_name
                        ?.charAt(0)
                        .toUpperCase()
                }

            </div>

            <div className="conversation-info">

                <h4>

                    {user.display_name}

                </h4>

                <p>

                    {
                        conversation.last_message
                            ? "🔒 Encrypted message"
                            : "No messages yet"
                    }

                </p>

            </div>

            {unread > 0 ? (

                <span className="unread-badge">

                    {unread}

                </span>

            ) : null}

        </div>

    );

}