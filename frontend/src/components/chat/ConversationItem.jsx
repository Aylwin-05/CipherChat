import "./ConversationList.css";

export default function ConversationItem({

    conversation,
    selected,
    onSelect,

}) {

    return (

        <div
            className={
                selected
                    ? "conversation-item active"
                    : "conversation-item"
            }
            onClick={() =>
                onSelect(conversation)
            }
        >

            <div className="conversation-avatar">

                💬

            </div>

            <div className="conversation-info">

                <h4>

                    Conversation

                </h4>

                <p>

                    {conversation.id}

                </p>

            </div>

        </div>

    );

}