import { useAuth } from "../../context/AuthContext";
import { useEffect, useState } from "react";
import attachmentService from "../../services/attachmentService";

export default function MessageBubble({ message }) {

    const { user } = useAuth();

    const [attachmentUrls, setAttachmentUrls] = useState({});

    // ==========================================================
    // Load attachment blobs (authenticated)
    // ==========================================================

    useEffect(() => {

        async function loadAttachments() {

            const urls = {};

            for (const attachment of message.attachments || []) {

                try {

                    urls[attachment.id] =
                        await attachmentService.getAttachment(
                            attachment.id
                        );

                }

                catch (err) {

                    console.error(
                        "Attachment load failed:",
                        err
                    );

                }

            }

            setAttachmentUrls(urls);

        }

        loadAttachments();

    }, [message]);

    // ==========================================================
    // Cleanup blob URLs
    // ==========================================================

    useEffect(() => {

        return () => {

            Object.values(attachmentUrls).forEach(url => {

                URL.revokeObjectURL(url);

            });

        };

    }, [attachmentUrls]);

    if (!message) return null;

    const isMine =
        String(user?.id) ===
        String(message.sender_id);

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

                    const url =
                        attachmentUrls[attachment.id];

                    if (!url) return null;

                    switch (attachment.attachment_type) {

                        case "image":

                            return (

                                <img
                                    key={attachment.id}
                                    src={url}
                                    alt={attachment.original_name}
                                    className="chat-image"
                                />

                            );

                        case "voice":

                        case "audio":

                            return (

                                <audio
                                    key={attachment.id}
                                    controls
                                    src={url}
                                    className="chat-audio"
                                />

                            );

                        case "video":

                            return (

                                <video
                                    key={attachment.id}
                                    controls
                                    src={url}
                                    className="chat-video"
                                />

                            );

                        default:

                            return (

                                <a
                                    key={attachment.id}
                                    href={url}
                                    download={attachment.original_name}
                                >
                                    📄 {attachment.original_name}
                                </a>

                            );

                    }

                })}

                {/* FOOTER */}

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