import { useAuth } from "../../context/AuthContext";
import { useEffect, useState } from "react";
import attachmentService from "../../services/attachmentService";
export default function MessageBubble({ message }) {
    const { user } = useAuth();
    const [imageUrls, setImageUrls] = useState({});
    useEffect(()=>{

        async function loadImages(){

            const urls={};

            for(
                const attachment of message.attachments || []
            ){

                if(
                    attachment.mime_type.startsWith("image")
                ){

                    urls[attachment.id]=
                        await attachmentService.getImage(
                            attachment.id
                        );

                }

            }

            setImageUrls(urls);

        }

        loadImages();

    },[message]);

    useEffect(() => {

        return () => {

            Object.values(imageUrls).forEach(

                (url)=>
                    URL.revokeObjectURL(url)

            );

        };

    },[imageUrls]);
    if (!message) return null;

    const isMine =
        String(user?.id) ===
        String(message?.sender_id);

    const content =
        message.deleted_for_everyone
            ? "🚫 Message deleted"
            : message.content;

    return (

        <div
            className={`message-row ${isMine ? "mine" : "other"}`}
        >

            <div
                className={`message-bubble ${isMine ? "mine" : "other"}`}
            >

                {/* TEXT */}

                {content && (

                    <div className="message-content">

                        {content}

                    </div>

                )}

                {/* ATTACHMENTS */}

                {message.attachments?.map((attachment) => {

                    if (attachment.attachment_type === "image") {

                        return (

                            <img
                                key={attachment.id}
                                src={imageUrls[attachment.id]}
                                className="chat-image"
                                alt={attachment.original_name}
                            />

                        );

                    }

                    return (

                        <a
                            key={attachment.id}
                            href={attachmentService.downloadUrl(
                                attachment.id
                            )}
                            target="_blank"
                            rel="noreferrer"
                        >
                            📄 {attachment.original_name}
                        </a>

                    );

                })}

                <div className="message-footer">

                    <span className="message-time">

                        {new Date(
                            message.created_at
                        ).toLocaleTimeString([], {

                            hour: "2-digit",

                            minute: "2-digit",

                        })}

                    </span>

                    {message.edited && (

                        <span className="message-edited">

                            Edited

                        </span>

                    )}

                    {isMine && (

                        <span className="message-status">

                            {message.is_read
                                ? "✓✓"
                                : message.delivered_at
                                    ? "✓✓"
                                    : "✓"}

                        </span>

                    )}

                </div>

            </div>

        </div>

    );

}