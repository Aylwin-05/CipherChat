export default function MessageBubble({
    message,
}) {

    return (

        <div className="message-bubble">

            <div className="message-content">

                {message.content}

            </div>

            <div className="message-time">

                {

                    new Date(
                        message.created_at
                    ).toLocaleTimeString()

                }

            </div>

        </div>

    );

}