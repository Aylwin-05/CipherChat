import UserAvatar from "../UserAvatar";

import "./ConversationList.css";

function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
    });
}

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
                    ? "conv-item active"
                    : "conv-item"
            }
            onClick={() => onSelect(conversation)}
        >

            <div className="conv-avatar">

                <UserAvatar
                    user={user}
                    className="conv-avatar-badge"
                >
                    <span className="presence-dot" />
                </UserAvatar>

            </div>

            <div className="conv-meta">

                <div className="conv-top">

                    <h4 className="conv-name">

                        {user?.display_name || "Unknown"}

                    </h4>

                    <span className="conv-time">

                        {formatTime(
                            conversation.last_message
                                ?.created_at ??
                            conversation.updated_at
                        )}

                    </span>

                </div>

                <div className="conv-bottom">

                    <p className="conv-preview">

                        {conversation.last_message
                            ? "Encrypted message"
                            : "No messages yet"}

                    </p>

                    {unread > 0 ? (

                        <span className="unread-pill">

                            {unread}

                        </span>

                    ) : null}

                </div>

            </div>

        </div>

    );

}