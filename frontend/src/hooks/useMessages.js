import {
    useEffect,
    useState,
} from "react";

import { useAuth } from "../context/AuthContext";

import messageService from "../services/messageService";
import websocketService from "../services/websocketService";
import keyService from "../services/keyService";
import attachmentService from "../services/attachmentService";
import { encryptFile } from "../utils/fileEncryption";
import {
    encryptMessage,
    decryptMessage,
} from "../crypto/cryptoService";
import {
    getPrivateKey,
} from "../crypto/keyStorage";

export default function useMessages(
    conversation,
    onNewMessage,
) {

    const { user } = useAuth();

    const [messages, setMessages] =
        useState([]);

    const [imageUrls, setImageUrls] =
        useState({});

    const [typingUsers, setTypingUsers] =
        useState([]);

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState(null);

    useEffect(() => {

        if (!conversation) {

            setMessages([]);

            websocketService.disconnect();

            return;

        }

        void initialize();

        return () => {

            websocketService.disconnect();

        };

    }, [conversation?.id]);
    useEffect(() => {

    return () => {

        Object.values(imageUrls).forEach(

            (url) => URL.revokeObjectURL(url)

        );

    };

    }, [imageUrls]);

    async function initialize() {

        try {

            setLoading(true);

            //--------------------------------------------------
            // Load encrypted history
            //--------------------------------------------------

            const history =
                await messageService.getMessages(
                    conversation.id
                );

            //--------------------------------------------------
            // Decrypt every message
            //--------------------------------------------------

            const decrypted =
                await Promise.all(

                    history.map(
                        async (message) => {

                            try {

                        const encryptedKey =
                            message.sender_id === user.id
                                ? message.encrypted_key_sender
                                : message.encrypted_key_receiver;

                        const plaintext =
                            await decryptMessage(
                                message.ciphertext,
                                encryptedKey,
                                message.nonce,
                                getPrivateKey()
                            );

                                return {

                                    ...message,

                                    content:
                                        plaintext,

                                };

                            }

                            catch {

                                return {

                                    ...message,

                                    content:
                                        "[Unable to decrypt]",

                                };

                            }

                        }

                    )

                );

            setMessages(decrypted);
            //--------------------------------------------------
            // Download all image attachments
            //--------------------------------------------------

            for (const message of decrypted) {

                if (!message.attachments?.length) {

                    continue;

                }

                for (const attachment of message.attachments) {

                    if (
                        attachment.attachment_type ===
                        "image"
                    ) {

                        try {

                            const imageUrl =
                                await attachmentService.getAttachment(
                                    attachment.id
                                );

                            setImageUrls(previous => ({

                                ...previous,

                                [attachment.id]:
                                    imageUrl,

                            }));

                        }

                        catch (error) {

                            console.error(
                                "Image download failed",
                                error
                            );

                        }

                    }

                }

            }

            //--------------------------------------------------
            // Connect websocket
            //--------------------------------------------------

            const token =
                localStorage.getItem(
                    "access_token"
                );

            websocketService.connect(
                conversation.id,
                token,
            );

            //--------------------------------------------------
            // Listen websocket
            //--------------------------------------------------

            websocketService.onMessage(

                async (event) => {
                                        switch (event.event) {

                        //--------------------------------------------------
                        // Connected
                        //--------------------------------------------------

                        case "connected":

                            break;

                        //--------------------------------------------------
                        // Incoming encrypted message
                        //--------------------------------------------------

                        case "message":

                            try {

                            const encryptedKey =
                                event.sender_id === user.id
                                    ? event.encrypted_key_sender
                                    : event.encrypted_key_receiver;

                            const plaintext =
                                await decryptMessage(
                                    event.ciphertext,
                                    encryptedKey,
                                    event.nonce,
                                    getPrivateKey()
                                );

                                const message = {

                                    ...event,

                                    content: plaintext,

                                    attachments:
                                        event.attachments || [],


                                };

                                setMessages(
                                    previous => {

                                        const exists =
                                            previous.some(
                                                msg =>
                                                    msg.id ===
                                                    message.id
                                            );

                                        if (exists) {

                                            return previous;

                                        }

                                        return [

                                            ...previous,

                                            message,

                                        ];

                                    }
                                );

                                onNewMessage?.(
                                    message
                                );

                            }

                            catch (error) {

                                console.error(
                                    "Decrypt failed",
                                    error
                                );

                            }

                            break;

                        //--------------------------------------------------
                        // Typing
                        //--------------------------------------------------

                        case "typing":

                            if (
                                event.user_id !==
                                user?.id
                            ) {

                                setTypingUsers(
                                    previous => {

                                        if (
                                            previous.includes(
                                                event.user_id
                                            )
                                        ) {

                                            return previous;

                                        }

                                        return [

                                            ...previous,

                                            event.user_id,

                                        ];

                                    }
                                );

                            }

                            break;

                        //--------------------------------------------------
                        // Stop Typing
                        //--------------------------------------------------

                        case "stop_typing":

                            setTypingUsers(
                                previous =>

                                    previous.filter(
                                        id =>
                                            id !==
                                            event.user_id
                                    )

                            );

                            break;

                        //--------------------------------------------------
                        // Edit
                        //--------------------------------------------------

                        case "edit":

                            setMessages(
                                previous =>

                                    previous.map(
                                        message =>

                                            message.id ===
                                            event.message_id

                                                ? {

                                                    ...message,

                                                    edited: true,

                                                    updated_at:
                                                        event.updated_at,

                                                }

                                                : message

                                    )

                            );

                            break;

                        //--------------------------------------------------
                        // Delete
                        //--------------------------------------------------

                        case "delete":

                            setMessages(
                                previous =>

                                    previous.map(
                                        message =>

                                            message.id ===
                                            event.message_id

                                                ? {

                                                    ...message,

                                                    deleted_for_everyone: true,

                                                    content:
                                                        "🚫 Message deleted",

                                                }

                                                : message

                                    )

                            );

                            break;

                        //--------------------------------------------------
                        // Delivered
                        //--------------------------------------------------

                        case "delivered":

                            setMessages(
                                previous =>

                                    previous.map(
                                        message =>

                                            message.id ===
                                            event.message_id

                                                ? {

                                                    ...message,

                                                    delivered_at:
                                                        event.delivered_at,

                                                }

                                                : message

                                    )

                            );

                            break;

                        //--------------------------------------------------
                        // Read
                        //--------------------------------------------------

                        case "read":

                            setMessages(
                                previous =>

                                    previous.map(
                                        message =>

                                            message.id ===
                                            event.message_id

                                                ? {

                                                    ...message,

                                                    is_read: true,

                                                    read_at:
                                                        event.read_at,

                                                }

                                                : message

                                    )

                            );
                            case "attachment":

                            if (
                                event.attachment?.attachment_type ===
                                "image"
                            ) {

                                try {

                                    const imageUrl =
                                        await attachmentService.getAttachment(
                                            event.attachment.id
                                        );

                                    setImageUrls(previous => ({

                                        ...previous,

                                        [event.attachment.id]:
                                            imageUrl,

                                    }));

                                }

                                catch (error) {

                                    console.error(error);

                                }

                            }

                            setMessages(previous =>

                                previous.map(message =>

                                    message.id ===
                                    event.message_id

                                        ? {

                                            ...message,

                                            attachments: [

                                                ...(message.attachments || []),

                                                event.attachment,

                                            ],

                                        }

                                        : message

                                )

                            );

                            break;
                        //--------------------------------------------------
                        // Attachment
                        //--------------------------------------------------

                        case "attachment":

                            setMessages(previous =>

                                previous.map(message =>

                                    message.id === event.message_id

                                        ? {

                                            ...message,

                                            attachments: [

                                                ...(message.attachments || []),

                                                event.attachment,

                                            ],

                                        }

                                        : message

                                )

                            );

                            break;

                            //--------------------------------------------------
                            // Attachment Deleted
                            //--------------------------------------------------

                            case "attachment_deleted":

                                setMessages(previous =>

                                    previous.map(message =>

                                        message.id === event.message_id

                                            ? {

                                                ...message,

                                                attachments:

                                                    (message.attachments || []).filter(

                                                        attachment =>

                                                            attachment.id !== event.attachment_id

                                                    ),

                                            }

                                            : message

                                    )

                                );

                                break;

                        default:

                            break;

                    }

                }

            );

        }

        catch (err) {

            console.error(err);

            setError(err);

        }

        finally {

            setLoading(false);

        }

    }
        //--------------------------------------------------
    // Send Encrypted Message
    //--------------------------------------------------

    async function sendMessage(
        plaintext,
        file = null,
    )
    {

        try {

            //------------------------------------------
            // Fetch recipient public key
            //------------------------------------------

            const receiver =
                await keyService.getPublicKey(
                    conversation.other_user.id
                );

            const senderPublicKey =
                localStorage.getItem(
                    "cipherchat_public_key"
                );

            const encrypted =
                await encryptMessage(
                    plaintext,
                    senderPublicKey,
                    receiver.public_key
                );

            //------------------------------------------
            // Save encrypted payload via REST
            //------------------------------------------

            console.log("3. Sending to backend...");

            const saved =
                await messageService.sendMessage(
                    conversation.id,
                    encrypted,
                );

            console.log("Backend response:", saved);

            // ==========================================
            // Upload attachment (if selected)
            // ==========================================

            let upload = null;

            if (file) {

                console.log("Encrypting attachment...");

                const encryptedAttachment =
                    await encryptFile(file);

                const encryptedFile =
                    new File(

                        [
                            encryptedAttachment.encryptedFile,
                        ],

                        file.name + ".bin",

                        {
                            type: "application/octet-stream",
                        }

                    );

                upload =
                    await messageService.uploadAttachment(

                        saved.id,

                        encryptedFile,

                    );

                console.log(
                    "Encrypted attachment uploaded:",
                    upload
                );

                // Save for next step (RSA encryption)

                upload.encryption = {

                    rawKey:
                        encryptedAttachment.rawKey,

                    iv:
                        encryptedAttachment.iv,

                };

            }

            //------------------------------------------
            // Show instantly for sender
            //------------------------------------------

            const localMessage = {

                ...saved,

                content: plaintext,

                attachments: file && upload
                    ? [
                        upload.attachment
                    ]
                    : [],

            };

            setMessages(

                previous => [

                    ...previous,

                    localMessage,

                ]

            );

            onNewMessage?.(
                localMessage
            );

            //------------------------------------------
            // Broadcast encrypted payload
            //------------------------------------------

        websocketService.sendMessage({

            id: saved.id,

            conversation_id:
                saved.conversation_id,

            sender_id:
                saved.sender_id,

            ciphertext:
                saved.ciphertext,

            encrypted_key_sender:
                saved.encrypted_key_sender,

            encrypted_key_receiver:
                saved.encrypted_key_receiver,

            nonce:
                saved.nonce,

            crypto_version:
                saved.crypto_version,

            message_type:
                saved.message_type,

            reply_to_id:
                saved.reply_to_id,

            created_at:
                saved.created_at,

            attachments:
                localMessage.attachments,

        });

        }

        catch (error) {

            console.error(
                "Failed to send message",
                error
            );

            setError(error);

        }

    }

    //--------------------------------------------------
    // Typing
    //--------------------------------------------------

    function typing() {

        websocketService.sendTyping();

    }

    //--------------------------------------------------
    // Stop Typing
    //--------------------------------------------------

    function stopTyping() {

        websocketService.stopTyping();

    }
        //--------------------------------------------------
    // Return Hook API
    //--------------------------------------------------

    return {

        messages,

        imageUrls,

        typingUsers,

        loading,

        error,

        sendMessage,

        typing,

        stopTyping,

    };

}