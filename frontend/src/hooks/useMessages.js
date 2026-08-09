import {
    useEffect,
    useState,
} from "react";

import { useAuth } from "../context/AuthContext";

import messageService from "../services/messageService";
import websocketService from "../services/websocketService";
import attachmentService from "../services/attachmentService";
import deviceService from "../services/deviceService";
import {
    getAccessToken,
} from "../api/api";
import {
    replenishPreKeys,
} from "../services/signalService";
import {
    encryptForConversation,
    decryptMessage as signalDecryptMessage,
} from "../services/signalChatService";
import {
    signalKeyStore,
} from "../crypto/signal/keyStore";
import {
    encryptFile,
    wrapFileKey,
} from "../utils/fileEncryption";
import keyService from "../services/keyService";
import {
    arrayBufferToBase64,
} from "../crypto/base64";
import {
    decryptMessage,
} from "../crypto/cryptoService";
import {
    getPrivateKey,
    getPublicKey,
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

    const [presence, setPresence] =
        useState({});

    const [loading, setLoading] =
        useState(false);

    const [error, setError] =
        useState(null);

    //------------------------------------------------------
    // Decrypt an incoming message (Signal first, RSA fallback)
    //------------------------------------------------------

    async function decryptIncoming(message) {

        const conversationId =
            message.conversation_id || conversation.id;

        // -------------------------------------------------
        // Plaintext cache first. Some envelopes are
        // fundamentally NOT replayable after a reload:
        //  - our own sends (no (me, me) ratchet session)
        //  - the first received handshake, whose one-time
        //    prekey was consumed and deleted on first use
        // So whatever we sent or actually decrypted is kept
        // in the local cache and served from there.
        // -------------------------------------------------

        const cached =
            await signalKeyStore.getPlaintext(
                conversationId,
                message.id,
            );

        if (cached != null) {

            return cached;

        }

        let plaintext;

        try {

            // Signal envelope JSON?
            plaintext = await signalDecryptMessage({
                conversationId,
                senderId: message.sender_id,
                ciphertext: message.ciphertext,
            });

        }
        catch {

            // Legacy RSA fallback
            try {

                const encryptedKey =
                    message.sender_id === user.id
                        ? message.encrypted_key_sender
                        : message.encrypted_key_receiver;

                plaintext = await decryptMessage(
                    message.ciphertext,
                    encryptedKey,
                    message.nonce,
                    getPrivateKey()
                );

            }
            catch {

                return "[Unable to decrypt]";

            }

        }

        // Decrypted live — remember it so a page reload can
        // show it again (the handshake envelope can never be
        // decrypted twice).
        try {

            await signalKeyStore.savePlaintext(
                conversationId,
                message.id,
                plaintext,
            );

        }
        catch (error) {

            console.error(
                "Failed to cache received message:",
                error
            );

        }

        return plaintext;

    }

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

                                const plaintext =
                                    await decryptIncoming(message);

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
            // Read receipts: opening a chat reads its history
            //--------------------------------------------------

            const latestIncoming =
                decrypted
                    .filter(
                        message =>
                            message.sender_id !== user?.id &&
                            !message.is_read
                    )
                    .sort(
                        (a, b) =>
                            new Date(a.created_at) -
                            new Date(b.created_at)
                    )
                    .pop();

            if (latestIncoming) {

                websocketService.sendRead(
                    latestIncoming.id
                );

            }

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
                getAccessToken();

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
                        // Presence (live online/offline)
                        //--------------------------------------------------

                        case "presence":

                            if (
                                event.user_id &&
                                event.user_id !== user?.id
                            ) {

                                setPresence(previous => ({

                                    ...previous,

                                    [event.user_id]:
                                        event.online,

                                }));

                            }

                            break;

                        //--------------------------------------------------
                        // Incoming encrypted message
                        //--------------------------------------------------

                        case "message":

                            try {

                            const plaintext =
                                await decryptIncoming(event);

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

                                //------------------------------------------
                                // Read receipts: the chat is open, so the
                                // incoming message is seen instantly.
                                //------------------------------------------

                                if (
                                    event.sender_id !== user?.id
                                ) {

                                    websocketService.sendDelivered(
                                        message.id
                                    );

                                    websocketService.sendRead(
                                        message.id
                                    );

                                }

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

                            break;

                            case "attachment":

                            if (
                                event.attachment?.attachment_type ===
                                "image"
                            ) {

                                try {

                                    const imageUrl =
                                        await attachmentService.getAttachment(
                                            event.attachment.id,
                                            {
                                                wrappedKey:
                                                    event.sender_id === user?.id
                                                        ? event.attachment.encrypted_key_sender
                                                        : event.attachment.encrypted_key_receiver,

                                                nonce:
                                                    event.attachment.nonce,
                                            }
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

                                                ...(message.attachments || []).filter(
                                                    attachment =>
                                                        attachment.id !==
                                                        event.attachment.id
                                                ),

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
            // Signal-encrypt for the recipient
            //------------------------------------------

            const encrypted =
                await encryptForConversation({
                    conversationId: conversation.id,
                    otherUserId: conversation.other_user.id,
                    plaintext,
                    bundleProvider: async () =>
                        deviceService.getBundle(
                            conversation.other_user.id
                        ),
                });

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

                // -----------------------------------------------
                // Upload the CIPHERTEXT under the original
                // filename: the backend derives the attachment
                // type from the extension (it never inspects
                // content), so an image must keep its .jpg to
                // be stored/typed as an image. The bytes on
                // disk are still AES ciphertext under a UUID
                // name.
                // -----------------------------------------------

                const encryptedFile =
                    new File(

                        [
                            encryptedAttachment.encryptedFile,
                        ],

                        file.name,

                        {
                            type:
                                file.type ||
                                "application/octet-stream",
                        }

                    );

                // -----------------------------------------------
                // Wrap the file's AES key for both participants
                // (RSA-OAEP). The backend only ever stores the
                // wraps + IV, never the raw key or plaintext.
                // -----------------------------------------------

                const senderPublicKey =
                    getPublicKey();

                const recipientKeyResponse =
                    await keyService.getPublicKey(
                        conversation.other_user.id
                    );

                const recipientPublicKey =
                    recipientKeyResponse?.public_key;

                if (
                    !senderPublicKey ||
                    !recipientPublicKey
                ) {

                    throw new Error(
                        "End-to-end encryption keys are not set up."
                    );

                }

                const [encryptedKeySender, encryptedKeyReceiver] =
                    await Promise.all([

                        wrapFileKey(
                            encryptedAttachment.rawKey,
                            senderPublicKey,
                        ),

                        wrapFileKey(
                            encryptedAttachment.rawKey,
                            recipientPublicKey,
                        ),

                    ]);

                upload =
                    await messageService.uploadAttachment(

                        saved.id,

                        encryptedFile,

                        {
                            encrypted_key_sender:
                                encryptedKeySender,

                            encrypted_key_receiver:
                                encryptedKeyReceiver,

                            nonce:
                                arrayBufferToBase64(
                                    encryptedAttachment.iv
                                ),

                        }

                    );

                console.log(
                    "Encrypted attachment uploaded:",
                    upload
                );

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
            // Cache our own plaintext so history shows it
            // after a refresh (senders cannot re-decrypt
            // their own ratchet envelopes). Must happen
            // before the broadcast — the WebSocket echoes
            // our own message back and the decrypt path
            // reads from this cache.
            //------------------------------------------

            try {

                await signalKeyStore.savePlaintext(
                    conversation.id,
                    saved.id,
                    plaintext,
                );

            }

            catch (error) {

                console.error(
                    "Failed to cache sent message:",
                    error
                );

            }

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

            //------------------------------------------
            // Clear any stale error from a previous send
            //------------------------------------------

            if (error) {

                setError(null);

            }

            //------------------------------------------
            // Keep the one-time prekey pool topped up
            //------------------------------------------

            replenishPreKeys()
                .catch((error) =>
                    console.error(
                        "One-time prekey replenishment failed:",
                        error
                    )
                );

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

        presence,

        loading,

        error,

        sendMessage,

        typing,

        stopTyping,

    };

}