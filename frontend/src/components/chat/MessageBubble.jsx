import { useAuth } from "../../context/AuthContext";
import { useEffect, useRef, useState } from "react";
import attachmentService from "../../services/attachmentService";
import ImageLightbox from "./ImageLightbox";

// ==========================================================
// Quick-reaction emoji row (WhatsApp-style)
// ==========================================================

const REACTION_EMOJIS = [
    "👍",
    "❤️",
    "😂",
    "😮",
    "😢",
    "🙏",
];

// ==========================================================
// Snippet used in the reply quote preview
// ==========================================================

function messageSnippet(message) {

    if (!message) return "";

    if (message.deleted_for_everyone) {
        return "Message deleted";
    }

    if (message.content) {
        return message.content;
    }

    if (message.attachments?.length) {
        const attachment = message.attachments[0];
        const kinds = {
            image: "Photo",
            voice: "Voice message",
            audio: "Audio message",
            video: "Video message",
        };
        return kinds[attachment.attachment_type] ||
            attachment.original_name ||
            "Attachment";
    }

    return "";

}

export default function MessageBubble({
    message,
    onDelete,
    onReply,
    onEdit,
    onForward,
    onToggleReaction,
    repliedMessage,
    repliedDisplayName = "",
    groupInfo = {},
}) {

    const { user } = useAuth();

    const [attachmentUrls, setAttachmentUrls] = useState({});

    const [lightbox, setLightbox] = useState(null);

    const [menuOpen, setMenuOpen] = useState(false);

    const [confirming, setConfirming] = useState(null);

    // Close the actions menu when clicking elsewhere
    useEffect(() => {

        if (!menuOpen) return;

        function closeMenu() {

            setMenuOpen(false);

            setConfirming(null);

        }

        document.addEventListener(
            "click",
            closeMenu,
        );

        return () => {

            document.removeEventListener(
                "click",
                closeMenu,
            );

        };

    }, [menuOpen]);

    // ==========================================================
    // Delete actions
    // ==========================================================

    async function handleAction(scope) {

        // "Delete for everyone" needs a second tap to confirm
        if (
            scope === "everyone" &&
            confirming !== "everyone"
        ) {

            setConfirming("everyone");

            return;

        }

        setMenuOpen(false);

        setConfirming(null);

        await onDelete?.(
            message.id,
            scope,
        );

    }

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

    // --------------------------------------------------------
    // What can this message do?
    // --------------------------------------------------------

    const isText =
        Boolean(content) &&
        content !== "[Unable to decrypt]" &&
        !deleted;

    const canEdit =
        isMine && isText;

    const canForward =
        isText;

    // --------------------------------------------------------
    // Reactions: grouped chips with counts
    // --------------------------------------------------------

    const myReaction =
        (message.reactions || []).find(
            reaction =>
                reaction.user_id ===
                String(user?.id)
        );

    const reactionGroups =
        Object.values(
            (message.reactions || []).reduce(
                (groups, reaction) => {

                    if (!groups[reaction.emoji]) {

                        groups[reaction.emoji] = {
                            emoji: reaction.emoji,
                            count: 0,
                            mine: false,
                        };

                    }

                    groups[reaction.emoji].count += 1;

                    if (
                        reaction.user_id ===
                        String(user?.id)
                    ) {

                        groups[reaction.emoji].mine = true;

                    }

                    return groups;

                },
                {},
            )
        );

    const repliedSenderName =
        repliedDisplayName ||
        (repliedMessage?.sender_id === user?.id
            ? "You"
            : "Unknown");

    const messageRowClass = [
        "message-row",
        isMine ? "mine" : "other",
        groupInfo.firstInGroup
            ? "first-in-group"
            : "",
        groupInfo.lastInGroup
            ? "last-in-group"
            : "",
    ].join(" ");

    return (

        <div className={messageRowClass}>

            <div
                className={[
                    "message-bubble",
                    isMine ? "mine" : "other",
                    deleted ? "deleted" : "",
                    groupInfo.lastInGroup
                        ? "tail"
                        : "",
                ].join(" ")}
            >

                {/* SENDER NAME (grouped other chats) */}

                {!isMine &&
                    groupInfo.showName &&
                    !deleted && (

                        <span className="message-sender-name">

                            {groupInfo.displayName ||
                                "Unknown"}

                        </span>

                    )}

                {/* FORWARDED LABEL */}

                {message.is_forwarded && !deleted && (

                    <span className="message-forwarded">

                        Forwarded

                    </span>

                )}

                {/* ACTIONS MENU */}

                {!deleted && (

                    <div
                        className={`bubble-actions ${
                            menuOpen ? "open" : ""
                        }`}
                    >

                        <button
                            type="button"
                            className="bubble-actions-btn"
                            aria-label="Message actions"
                            onClick={(event) => {

                                event.stopPropagation();

                                setMenuOpen(open => !open);

                                setConfirming(null);

                            }}
                        >

                            <svg
                                width="16"
                                height="16"
                                viewBox="0 0 24 24"
                                fill="currentColor"
                            >
                                <circle cx="5" cy="12" r="1.7" />
                                <circle cx="12" cy="12" r="1.7" />
                                <circle cx="19" cy="12" r="1.7" />
                            </svg>

                        </button>

                        {menuOpen && (

                            <div
                                className="bubble-menu"
                                onClick={(event) =>
                                    event.stopPropagation()
                                }
                            >

                                {/* QUICK REACTIONS */}

                                <div className="bubble-reactions-row">

                                    {REACTION_EMOJIS.map(emoji => {

                                        const active =
                                            myReaction?.emoji ===
                                            emoji;

                                        return (

                                            <button
                                                key={emoji}
                                                type="button"
                                                className={[
                                                    "bubble-reaction-btn",
                                                    active
                                                        ? "active"
                                                        : "",
                                                ].join(" ")}
                                                aria-label={`React ${emoji}`}
                                                onClick={() => {

                                                    setMenuOpen(false);

                                                    onToggleReaction?.(
                                                        message.id,
                                                        emoji,
                                                    );

                                                }}
                                            >

                                                {emoji}

                                            </button>

                                        );

                                    })}

                                </div>

                                <button
                                    type="button"
                                    className="bubble-menu-item"
                                    onClick={() => {

                                        setMenuOpen(false);

                                        onReply?.(message);

                                    }}
                                >

                                    Reply

                                </button>

                                {canEdit && (

                                    <button
                                        type="button"
                                        className="bubble-menu-item"
                                        onClick={() => {

                                            setMenuOpen(false);

                                            onEdit?.(message);

                                        }}
                                    >

                                        Edit

                                    </button>

                                )}

                                {canForward && (

                                    <button
                                        type="button"
                                        className="bubble-menu-item"
                                        onClick={() => {

                                            setMenuOpen(false);

                                            onForward?.(message);

                                        }}
                                    >

                                        Forward

                                    </button>

                                )}

                                <button
                                    type="button"
                                    className="bubble-menu-item"
                                    onClick={() =>
                                        handleAction("me")
                                    }
                                >

                                    Delete for me

                                </button>

                                {isMine && (

                                    <button
                                        type="button"
                                        className={[
                                            "bubble-menu-item",
                                            "danger",
                                            confirming === "everyone"
                                                ? "confirm"
                                                : "",
                                        ].join(" ")}
                                        onClick={() =>
                                            handleAction("everyone")
                                        }
                                    >

                                        {confirming === "everyone"
                                            ? "Tap again to confirm"
                                            : "Delete for everyone"}

                                    </button>

                                )}

                            </div>

                        )}

                    </div>

                )}

                {/* REPLY PREVIEW */}

                {message.reply_to_id &&
                    repliedMessage &&
                    !deleted && (

                        <div className="message-reply-preview">

                            <div className="message-reply-accent" />

                            <div className="message-reply-body">

                                <span className="message-reply-name">

                                    {repliedSenderName}

                                </span>

                                <span className="message-reply-text">

                                    {messageSnippet(
                                        repliedMessage
                                    )}

                                </span>

                            </div>

                        </div>

                    )}

                {/* TEXT */}

                {content && !deleted && (

                    <div className="message-content">

                        {content}

                    </div>

                )}

                {content && deleted && (

                    <div className="message-content deleted-content">

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

                {/* REACTION CHIPS */}

                {reactionGroups.length > 0 && !deleted && (

                    <div className="message-reactions">

                        {reactionGroups.map(group => (

                            <button
                                key={group.emoji}
                                type="button"
                                className={[
                                    "reaction-chip",
                                    group.mine ? "mine" : "",
                                ].join(" ")}
                                title={
                                    group.mine
                                        ? "Tap to remove"
                                        : ""
                                }
                                onClick={() => {

                                    if (group.mine) {

                                        onToggleReaction?.(
                                            message.id,
                                            group.emoji,
                                        );

                                    }

                                }}
                            >

                                <span className="reaction-chip-emoji">

                                    {group.emoji}

                                </span>

                                {group.count > 1 && (

                                    <span className="reaction-chip-count">

                                        {group.count}

                                    </span>

                                )}

                            </button>

                        ))}

                    </div>

                )}

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
