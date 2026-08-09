import { useAuth } from "../../context/AuthContext";
import { useEffect, useRef, useState } from "react";
import attachmentService from "../../services/attachmentService";
import ImageLightbox from "./ImageLightbox";

export default function MessageBubble({ message }) {

    const { user } = useAuth();

    const [attachmentUrls, setAttachmentUrls] = useState({});

    const [lightbox, setLightbox] = useState(null);

    // ==========================================================
    // Load attachment blobs (authenticated + decrypted)
    //
    // Reload only when the actual attachment set changes, NOT
    // when unrelated updates (read receipts, typing) remap the
    // message objects — otherwise old blob URLs get replaced
    // (and revoked) while the lightbox is still showing one.
    // ==========================================================

    const attachmentKey =
        `${message.id}:${(message.attachments || [])
            .map(attachment => attachment.id)
            .join(",")}`;

    const urlsRef = useRef({});

    useEffect(() => {

        let cancelled = false;

        async function loadAttachments() {

            const urls = {};

            for (const attachment of message.attachments || []) {

                try {

                    urls[attachment.id] =
                        await attachmentService.getAttachment(
                            attachment.id,
                            {
                                wrappedKey:
                                    message.sender_id === user?.id
                                        ? attachment.encrypted_key_sender
                                        : attachment.encrypted_key_receiver,

                                nonce:
                                    attachment.nonce,
                            }
                        );

                }

                catch (err) {

                    console.error(
                        "Attachment load failed:",
                        err
                    );

                }

            }

            if (cancelled) {

                Object.values(urls).forEach(url =>
                    URL.revokeObjectURL(url)
                );

                return;

            }

            setAttachmentUrls(urls);

        }

        loadAttachments();

        return () => {

            cancelled = true;

        };

    }, [attachmentKey, user?.id]);

    // ==========================================================
    // Cleanup blob URLs — only on unmount (switching messages
    // or leaving the chat), so live lightbox URLs stay valid.
    // ==========================================================

    useEffect(() => {

        urlsRef.current = attachmentUrls;

    }, [attachmentUrls]);

    useEffect(() => {

        return () => {

            Object.values(urlsRef.current).forEach(url => {

                URL.revokeObjectURL(url);

            });

        };

    }, []);

    if (!message) return null;

    const isMine =
        String(user?.id) ===
        String(message.sender_id);

    const deleted =
        message.deleted_for_everyone;

    const content = deleted
        ? "Message deleted"
        : message.content;

    return (

        <div
            className={`message-row ${isMine ? "mine" : "other"}`}
        >

            <div
                className={[
                    "message-bubble",
                    isMine ? "mine" : "other",
                    deleted ? "deleted" : "",
                ].join(" ")}
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
                                    onClick={() => setLightbox({
                                        attachment,
                                        url,
                                    })}
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
                                    className="message-attachment"
                                >

                                    <svg
                                        width="15"
                                        height="15"
                                        viewBox="0 0 24 24"
                                        fill="none"
                                        stroke="currentColor"
                                        strokeWidth="2"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    >
                                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
                                    </svg>

                                    {attachment.original_name}

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

                    {isMine && !deleted && (

                        <span
                            className={
                                message.is_read
                                    ? "message-status read"
                                    : "message-status"
                            }
                        >

                            {message.is_read
                                ? "✓✓"
                                : message.delivered_at
                                    ? "✓✓"
                                    : "✓"}

                        </span>

                    )}

                </div>

            </div>

            <ImageLightbox
                attachment={lightbox?.attachment}
                url={lightbox?.url}
                onClose={() =>
                    setLightbox(null)
                }
            />

        </div>

    );

}