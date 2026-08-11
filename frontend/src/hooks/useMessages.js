import {
    useEffect,
    useState,
} from "react";

import { useAuth } from "../context/AuthContext";

import messageService from "../services/messageService";
import conversationService from "../services/conversationService";
import websocketService from "../services/websocketService";
import {
    useChatSocket,
} from "../context/ChatSocketContext";
import attachmentService from "../services/attachmentService";
import deviceService from "../services/deviceService";
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

// ==========================================================
// Reaction list updater
//
// One reaction per user per message (WhatsApp-style): a new
// emoji replaces the previous one; toggling the same emoji
// removes it.
// ==========================================================

function applyReaction(message, event) {

    const reactions =
        (message.reactions || []).filter(
            reaction =>
                reaction.user_id !==
                String(event.user_id)
        );

    if (event.action === "add") {

        reactions.push({
            user_id: String(event.user_id),
            emoji: event.emoji,
            created_at: event.created_at ?? null,
        });

    }

    return {
        ...message,
        reactions,
    };

}

export default function useMessages(
    conversation,
    onNewMessage,
) {

    const { user } = useAuth();

    const { subscribe } = useChatSocket();

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

        const cachedRecord =
            await signalKeyStore.getCachedRecord(
                conversationId,
                message.id,
            );

        // The cache is keyed per message id. An EDITED message
        // carries a fresh envelope, so a record whose ciphertext
        // differs from the message's current ciphertext is stale
        // and must be re-decrypted instead of served from cache.
        // Records saved before ciphertext tracking (null) keep
        // matching so old cached history keeps its plaintext.
        if (
            cachedRecord &&
            (
                cachedRecord.ciphertext == null ||
                cachedRecord.ciphertext === message.ciphertext
            )
        ) {

            return cachedRecord.plaintext;

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

        // Decrypted live ΓÇö remember it so a page reload can
        // show it again (the handshake envelope can never be
        // decrypted twice).
        try {

            await signalKeyStore.savePlaintext(
                conversationId,
                message.id,
                plaintext,
                message.ciphertext,
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

            return;

        }

        void initialize();

    }, [conversation?.id]);
    useEffect(() => {

    return () => {

        Object.values(imageUrls).forEach(

            (url) => URL.revokeObjectURL(url)

        );

    };

    }, [imageUrls]);
    //------------------------------------------------------
    // Real-time events: the user-scoped socket (ChatSocket
    // provider) delivers every conversation; filter to this
    // one and apply updates without any page refresh.
    //------------------------------------------------------

    useEffect(() => {

        if (!conversation) return;

        const unsubscribe = subscribe(

            async (event) => {

                if (
                    event.conversation_id &&
                    event.conversation_id !== conversation.id
                ) {
                    return;
                }

                                        switch (event.event) {

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

                                    reactions:
                                        event.reactions || [],

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
                                        conversation.id,
                                        message.id
                                    );

                                    websocketService.sendRead(
                                        conversation.id,
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

                                                    ciphertext:
                                                        event.ciphertext ??
                                                        message.ciphertext,

                                                    encrypted_key_sender:
                                                        event.encrypted_key_sender ??
                                                        message.encrypted_key_sender,

                                                    encrypted_key_receiver:
                                                        event.encrypted_key_receiver ??
                                                        message.encrypted_key_receiver,

                                                    nonce:
                                                        event.nonce ??
                                                        message.nonce,

                                                }

                                                : message

                                    )

                            );

                            //-----------------------------------------------
                            // The edited content is a fresh ratchet
                            // envelope: try to decrypt it (receivers can,
                            // senders hit the plaintext cache).
                            //-----------------------------------------------

                            if (event.ciphertext) {

                                try {

                                    const updatedPlaintext =
                                        await decryptIncoming({

                                            id:
                                                event.message_id,

                                            conversation_id:
                                                conversation.id,

                                            sender_id:
                                                event.sender_id,

                                            ciphertext:
                                                event.ciphertext,

                                            encrypted_key_sender:
                                                event.encrypted_key_sender,

                                            encrypted_key_receiver:
                                                event.encrypted_key_receiver,

                                            nonce:
                                                event.nonce,

                                        });

                                    if (
                                        updatedPlaintext &&
                                        updatedPlaintext !==
                                            "[Unable to decrypt]"
                                    ) {

                                        setMessages(
                                            previous =>

                                                previous.map(
                                                    message =>

                                                        message.id ===
                                                        event.message_id

                                                            ? {

                                                                ...message,

                                                                content:
                                                                    updatedPlaintext,

                                                            }

                                                            : message

                                                )

                                        );

                                    }

                                }

                                catch (error) {

                                    console.error(
                                        "Edit decrypt failed",
                                        error
                                    );

                                }

                            }

                            break;

                        //--------------------------------------------------
                        // Reaction
                        //--------------------------------------------------

                        case "reaction":

                            setMessages(
                                previous =>

                                    previous.map(
                                        message =>

                                            message.id !==
                                            event.message_id

                                                ? message

                                                : applyReaction(
                                                    message,
                                                    event
                                                )

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
                                                        "≡ƒÜ½ Message deleted",

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

        return unsubscribe;

    }, [conversation?.id]);

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
                    conversation.id,
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
        options = {},
    )
    {

        const {
            replyToId = null,
            isForwarded = false,

        } = options;

        try {

            //--------------------------------------------------
            // Encrypt for the conversation (Signal ratchet)
            //--------------------------------------------------

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

            console.log(
                "3. Sending to backend..."
            );

            const saved =
                await messageService.sendMessage(
                    conversation.id,
                    encrypted,
                    replyToId,
                    isForwarded,
                );

            console.log(
                "Backend response:",
                saved
            );

            //--------------------------------------------------
            // Encrypt + upload attachment (if any)
            //--------------------------------------------------

            let uploaded = null;

            if (file) {

                console.log(
                    "Encrypting attachment..."
                );

                const {
                    encryptedFile,
                    rawKey,
                    iv,
                } = await encryptFile(file);

                const encryptedFileBlob =
                    new File(
                        [encryptedFile],
                        file.name,
                        {
                            type:
                                file.type ||
                                "application/octet-stream",
                        }
                    );

                const myPublicKey =
                    getPrivateKey();

                const theirPublicKey =
                    (
                        await keyService.getPublicKey(
                            conversation.other_user.id
                        )
                    )?.public_key;

                if (
                    !myPublicKey ||
                    !theirPublicKey
                ) {

                    throw new Error(
                        "End-to-end encryption keys are not set up."
                    );

                }

                const [
                    encryptedKeySender,
                    encryptedKeyReceiver,
                ] = await Promise.all([
                    wrapFileKey(rawKey, myPublicKey),
                    wrapFileKey(
                        rawKey,
                        theirPublicKey
                    ),
                ]);

                uploaded =
                    await messageService.uploadAttachment(
                        saved.id,
                        encryptedFileBlob,
                        {
                            encrypted_key_sender:
                                encryptedKeySender,

                            encrypted_key_receiver:
                                encryptedKeyReceiver,

                            nonce:
                                arrayBufferToBase64(iv),
                        }
                    );

                console.log(
                    "Encrypted attachment uploaded:",
                    uploaded
                );

            }

            //--------------------------------------------------
            // Optimistic UI + plaintext cache + realtime
            //--------------------------------------------------

            const localMessage = {
                ...saved,
                content: plaintext,
                attachments:
                    file && uploaded
                        ? [uploaded.attachment]
                        : [],
            };

            setMessages(previous => [
                ...previous,
                localMessage,
            ]);

            onNewMessage?.(localMessage);

            try {

                await signalKeyStore.savePlaintext(
                    conversation.id,
                    saved.id,
                    plaintext,
                    saved.ciphertext,
                );

            }
            catch (error) {

                console.error(
                    "Failed to cache sent message:",
                    error
                );

            }

            websocketService.sendMessage({
                id: saved.id,
                conversation_id: saved.conversation_id,
                sender_id: saved.sender_id,
                ciphertext: saved.ciphertext,
                encrypted_key_sender: saved.encrypted_key_sender,
                encrypted_key_receiver: saved.encrypted_key_receiver,
                nonce: saved.nonce,
                crypto_version: saved.crypto_version,
                message_type: saved.message_type,
                reply_to_id: saved.reply_to_id,
                is_forwarded: saved.is_forwarded,
                created_at: saved.created_at,
                attachments: localMessage.attachments,
            });

            if (error) setError(null);

            // Replenish one-time prekeys in the background
            replenishPreKeys().catch(
                error => console.error(
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

        websocketService.sendTyping(
            conversation.id
        );

    }

    //--------------------------------------------------
    // Stop Typing
    //--------------------------------------------------

    function stopTyping() {

        websocketService.stopTyping(
            conversation.id
        );

    }
        //--------------------------------------------------
    // Edit Message (end-to-end encrypted)
    //--------------------------------------------------

    async function editMessage(
        messageId,
        newPlaintext,
    ) {

        try {

            //--------------------------------------------------
            // Fresh ratchet envelope (the server never sees
            // the plaintext)
            //--------------------------------------------------

            const encrypted =
                await encryptForConversation({
                    conversationId: conversation.id,
                    otherUserId: conversation.other_user.id,
                    plaintext: newPlaintext,
                    bundleProvider: async () =>
                        deviceService.getBundle(
                            conversation.other_user.id
                        ),
                });

            await messageService.editMessage(
                messageId,
                encrypted,
            );

            // Optimistic UI update
            setMessages(
                previous => previous.map(
                    message =>

                        message.id === messageId

                            ? {

                                ...message,

                                content: newPlaintext,

                                edited: true,

                                ciphertext:
                                    encrypted.ciphertext,

                                encrypted_key_sender:
                                    encrypted.encrypted_key_sender,

                                encrypted_key_receiver:
                                    encrypted.encrypted_key_receiver,

                                nonce:
                                    encrypted.nonce,

                            }

                            : message
                )
            );

            try {

                await signalKeyStore.savePlaintext(
                    conversation.id,
                    messageId,
                    newPlaintext,
                    encrypted.ciphertext,
                );

            }
            catch (error) {

                console.error(
                    "Failed to cache edited message:",
                    error
                );

            }

            return true;

        }

        catch (error) {

            console.error(
                "Failed to edit message",
                error
            );

            setError(error);

            throw error;

        }

    }

    //--------------------------------------------------
    // Toggle Reaction (optimistic + rollback)
    //--------------------------------------------------

    async function toggleReaction(
        messageId,
        emoji,
    ) {

        const message = messages.find(
            message => message.id === messageId
        );

        const reaction = {
            message_id: messageId,
            user_id: user?.id,
            emoji,
            action:
                message?.reactions?.some(
                    reaction =>
                        reaction.user_id ===
                            String(user?.id) &&
                        reaction.emoji === emoji
                )
                    ? "remove"
                    : "add",
        };

        setMessages(
            previous => previous.map(
                message =>

                    message.id === messageId

                        ? applyReaction(
                            message,
                            reaction
                        )

                        : message
            )
        );

        try {

            await messageService.toggleReaction(
                messageId,
                emoji,
            );

        }
        catch (error) {

            console.error(
                "Failed to toggle reaction",
                error
            );

            setError(error);

            // Roll back the optimistic update
            setMessages(
                previous => previous.map(
                    message =>

                        message.id === messageId

                            ? applyReaction(
                                message,
                                {
                                    ...reaction,
                                    action:
                                        reaction.action === "add"
                                            ? "remove"
                                            : "add",
                                }
                            )

                            : message
                )
            );

        }

    }

    //--------------------------------------------------
    // Forward Message to multiple users
    //--------------------------------------------------

    async function forwardMessage(
        plaintext,
        targetUsers,
    ) {

        const results = [];

        try {

            for (const targetUser of targetUsers) {

                const targetConversation =
                    await conversationService.createPrivateConversation(
                        targetUser.id
                    );

                const encrypted =
                    await encryptForConversation({
                        conversationId: targetConversation.id,
                        otherUserId: targetUser.id,
                        plaintext,
                        bundleProvider: async () =>
                            deviceService.getBundle(
                                targetUser.id
                            ),
                    });

                const saved =
                    await messageService.sendMessage(
                        targetConversation.id,
                        encrypted,
                        null,
                        true,
                    );

                // The recipient's socket must see it in real
                // time, exactly like a normal send.
                websocketService.sendMessage({
                    id: saved.id,
                    conversation_id: saved.conversation_id,
                    sender_id: saved.sender_id,
                    ciphertext: saved.ciphertext,
                    encrypted_key_sender: saved.encrypted_key_sender,
                    encrypted_key_receiver: saved.encrypted_key_receiver,
                    nonce: saved.nonce,
                    crypto_version: saved.crypto_version,
                    message_type: saved.message_type,
                    reply_to_id: saved.reply_to_id,
                    is_forwarded: saved.is_forwarded,
                    created_at: saved.created_at,
                    attachments: [],
                });

                try {

                    await signalKeyStore.savePlaintext(
                        targetConversation.id,
                        saved.id,
                        plaintext,
                    );

                }

                catch (error) {

                    console.error(
                        "Failed to cache forwarded message:",
                        error
                    );

                }

                results.push({
                    conversation:
                        targetConversation,
                    message: saved,
                });

            }

            return results;

        }

        catch (error) {

            console.error(
                "Failed to forward message",
                error
            );

            setError(error);

            throw error;

        }

    }

    //--------------------------------------------------
    // Delete Message
    //--------------------------------------------------

    async function deleteMessage(
        messageId,
        scope,
    ) {

        try {

            if (scope === "everyone") {

                await messageService.deleteForEveryone(
                    messageId
                );

                //---------
                // Update own UI instantly
                //---------

                setMessages(
                    previous => previous.map(
                        message =>

                            message.id === messageId

                                ? {

                                    ...message,

                                    deleted_for_everyone: true,

                                    content:
                                        "Message deleted",

                                }

                                : message
                    )
                );

                //---------
                // Notify the other participant in real time
                //---------

                websocketService
                    .sendDelete(
                        conversation.id,
                        messageId
                    );

            }
            else {

                await messageService.deleteForMe(
                    messageId
                );

                //---------
                // "Delete for me" removes it from MY history
                //---------

                setMessages(
                    previous => previous.filter(
                        message =>
                            message.id !== messageId
                    )
                );

            }

        }

        catch (error) {

            console.error(
                "Failed to delete message",
                error
            );

            setError(error);

            throw error;

        }

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

        editMessage,

        toggleReaction,

        forwardMessage,

        deleteMessage,

        typing,

        stopTyping,

    };
}
