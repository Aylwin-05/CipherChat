import "./ConversationList.css";

export default function ConversationItem({

    conversation,
    selected,
    onSelect,

}) {

    const user = conversation.other_user;

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
                        conversation.last_message?.content ||
                        "No messages yet"
                    }

                </p>

            </div>

        </div>

    );

}