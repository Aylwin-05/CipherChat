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
    encryptForDevices,
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
import {
    encryptGroupMessage,
    decryptGroupMessage,
} from "../utils/groupEncryption";

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

    const [searchQuery, setSearchQuery] =
        useState("");

    const [searchResults, setSearchResults] =
        useState([]);

    const [searching, setSearching] =
        useState(false);

    const isGroup =
        conversation?.conversation_type === "group";

    // Group chats: participants (with public keys) fetched
    // from the backend, needed to wrap message keys at send.
    const [groupDetail, setGroupDetail] =
        useState(null);

    async function refreshGroupDetail() {

        if (!conversation || !isGroup) return;

        try {

            const detail =
                await conversationService.getConversation(
                    conversation.id
                );

            setGroupDetail(detail);

        }
        catch (error) {

            console.error(
                "Failed to load group detail",
                error
            );

        }

    }

    useEffect(() => {

        if (isGroup) {

            setGroupDetail(null);

            void refreshGroupDetail();

        }
        else {

            setGroupDetail(null);

        }

        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conversation?.id]);

    // Group membership always changes through a
    // `conversations_changed` event: re-fetch participants
    // so senders wrap keys for the CURRENT member set.
    useEffect(() => {

        if (!isGroup) return;

        const unsubscribe = subscribe(
            async (event) => {

                if (
                    event.event ===
                    "conversations_changed"
                ) {

                    await refreshGroupDetail();

                }

            }
        );

        return unsubscribe;

        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conversation?.id]);

    //------------------------------------------------------
    // Decrypt an incoming message (Signal first, RSA fallback)
    //------------------------------------------------------

    async function decryptIncoming(message) {

        const conversationId =
            message.conversation_id || conversation.id;

        // -------------------------------------------------
        // Multi-device: pick the envelope addressed to THIS
        // device. Messages carry one envelope per device of
        // every participant; only our own copy is decryptable
        // here. (Messages sent from another browser of this
        // account have a copy for us too — the sender wraps
        // for all devices.)
        // -------------------------------------------------

        const envelopes = message.envelopes ?? [];

        const meta = await signalKeyStore.getMeta();

        const myDeviceId = meta?.deviceId ?? null;

        const myEnvelope = myDeviceId
            ? envelopes.find(
                (entry) =>
                    entry.device_id === myDeviceId
              )?.data ?? null
            : null;

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

        // -------------------------------------------------
        // Group message: the AES key was wrapped to EVERY
        // member's device; unwrap OUR copy and decrypt.
        // (Determined by conversation type — modern group
        // messages may carry no legacy RSA recipient keys.)
        // -------------------------------------------------

        if (conversation?.conversation_type === "group") {

            // Per-device copies exist but none for THIS device
            // (e.g. history on a device registered later).
            if (envelopes.length && !myEnvelope) {

                return message.sender_id === user.id
                    ? "[Sent from another device]"
                    : "[Encrypted for another device]";

            }

            try {

                plaintext =
                    await decryptGroupMessage(
                        message,
                        getPrivateKey(),
                        user.id,
                        myDeviceId,
                    );

            }
            catch (error) {

                console.error(
                    "Failed to decrypt group message:",
                    error
                );

                return "[Unable to decrypt]";

            }

        }
        else if (myEnvelope) {

            //--------------------------------------------------
            // DM with a copy addressed to this device
            //--------------------------------------------------

            try {

                plaintext = await signalDecryptMessage({
                    conversationId,
                    senderId: message.sender_id,
                    ciphertext: myEnvelope,
                });

            }
            catch (error) {

                console.error(
                    "Failed to decrypt device envelope:",
                    error
                );

                return "[Unable to decrypt]";

            }

        }
        else if (envelopes.length) {

            //--------------------------------------------------
            // The message has per-device copies but none for
            // THIS device (e.g. old history on a browser that
            // registered after the message was sent). It was
            // never meant to be decryptable here.
            //--------------------------------------------------

            return message.sender_id === user.id
                ? "[Sent from another device]"
                : "[Encrypted for another device]";

        }
        else {

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

            clearSearch();

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
                        // Conversation deleted (two-party wipe)
                        //--------------------------------------------------

                        case "conversation_deleted":

                            setMessages([]);

                            clearSearch();

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

                                                    recipient_keys:
                                                        event.recipient_keys ??
                                                        message.recipient_keys ??
                                                        [],

                                                    envelopes:
                                                        event.envelopes ??
                                                        message.envelopes ??
                                                        [],

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

                                            recipient_keys:
                                                event.recipient_keys ?? [],

                                            envelopes:
                                                event.envelopes ?? [],

                                        });

                                    if (
                                        updatedPlaintext &&
                                        updatedPlaintext !==
                                            "[Unable to decrypt]" &&
                                        updatedPlaintext !==
                                            "[Sent from another device]" &&
                                        updatedPlaintext !==
                                            "[Encrypted for another device]"
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

    //------------------------------------------------------
    // Disappearing messages: drop messages locally when their
    // server-side expiry time arrives (the server also purges
    // the ciphertext on any read, so this is purely visual).
    //------------------------------------------------------

    useEffect(() => {

        if (!messages.length) return;

        const timers = [];

        for (const message of messages) {

            if (!message.expires_at) continue;

            const delay =
                new Date(message.expires_at) -
                Date.now();

            if (delay <= 0) {

                setMessages(previous =>
                    previous.filter(m =>
                        m.id !== message.id
                    )
                );

                continue;

            }

            timers.push(
                setTimeout(() => {

                    setMessages(previous =>
                        previous.filter(m =>
                            m.id !== message.id
                        )
                    );

                }, delay)
            );

        }

        return () => {
            timers.forEach(clearTimeout);
        };

    }, [messages]);

    //------------------------------------------------------
    // Search messages (client-side over decrypted plaintext).
    //
    // The backend can never match plaintext (it only stores
    // ciphertext), so the search fetches the conversation
    // history, decrypts each message through the Signal
    // session / plaintext cache, and filters locally. E2EE
    // means the search itself never leaves the device.
    //------------------------------------------------------

    async function searchMessages(query) {

        if (!query.trim()) {

            setSearchResults([]);

            setSearchQuery("");

            return;

        }

        setSearchQuery(query);

        setSearching(true);

        try {

            const history =
                await messageService.getMessages(
                    conversation.id
                );

            const needle =
                query.trim().toLowerCase();

            const matches = [];

            for (const message of history) {

                const plaintext =
                    await decryptIncoming(message);

                const haystack =
                    (plaintext ?? "").toLowerCase();

                if (haystack.includes(needle)) {

                    matches.push({
                        id: message.id,
                        content: plaintext,
                        created_at:
                            message.created_at,
                        sender_id:
                            message.sender_id,
                        message_type:
                            message.message_type,
                    });

                }

            }

            setSearchResults(matches);

        }
        catch (error) {

            console.error(
                "Search failed",
                error
            );

            setSearchResults([]);

            setError(error);

        }
        finally {

            setSearching(false);

        }

    }

    //------------------------------------------------------
    // Clear search state (switching chats, closing the bar)
    //------------------------------------------------------

    function clearSearch() {

        setSearchQuery("");

        setSearchResults([]);

    }

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
            // Group chats: fresh AES key wrapped to every
            // member's public key (E2EE for N recipients).
            //--------------------------------------------------

            if (isGroup) {

                if (file) {

                    throw new Error(
                        "Attachments are not available "
                        + "in group chats yet."
                    );

                }

                if (!groupDetail?.participants?.length) {

                    throw new Error(
                        "Group members are still loading. "
                        + "Try again in a moment."
                    );

                }

                const encrypted =
                    await encryptGroupMessage(
                        plaintext,
                        groupDetail.participants,
                        conversation.id,
                    );

                const saved =
                    await messageService.sendMessage(
                        conversation.id,
                        encrypted,
                        replyToId,
                        isForwarded,
                    );

                const localMessage = {
                    ...saved,
                    content: plaintext,
                    attachments: [],
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
                    expires_at: saved.expires_at,
                    created_at: saved.created_at,
                    attachments: [],
                    recipient_keys: saved.recipient_keys ?? [],
                    envelopes: saved.envelopes ?? [],
                });

                if (error) setError(null);

                return;

            }

            //--------------------------------------------------
            // Encrypt for EVERY device of both users (Signal
            // ratchet): one envelope per device, so this
            // account's other browsers can decrypt the echo.
            //--------------------------------------------------

            const [peerBundle, myBundle] = await Promise.all([
                deviceService.getBundle(
                    conversation.other_user.id
                ),
                deviceService.getBundle(
                    user.id
                ),
            ]);

            const allDevices = [
                ...(peerBundle?.devices ?? []),
                ...(myBundle?.devices ?? []),
            ];

            const encrypted =
                await encryptForDevices({
                    conversationId: conversation.id,
                    plaintext,
                    devices: allDevices,
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
                expires_at: saved.expires_at,
                created_at: saved.created_at,
                attachments: localMessage.attachments,
                recipient_keys: saved.recipient_keys ?? [],
                envelopes: saved.envelopes ?? [],
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

            let encrypted;

            let recipientKeys = [];

            //--------------------------------------------------
            // Group edit: fresh AES key wrapped to every member
            //--------------------------------------------------

            if (isGroup) {

                if (!groupDetail?.participants?.length) {

                    throw new Error(
                        "Group members are still loading. "
                        + "Try again in a moment."
                    );

                }

                encrypted =
                    await encryptGroupMessage(
                        newPlaintext,
                        groupDetail.participants,
                        conversation.id,
                    );

                recipientKeys =
                    encrypted.recipient_keys ?? [];

            }
            else {

                //--------------------------------------------------
                // Fresh per-device ratchet envelopes (the server
                // never sees the plaintext)
                //--------------------------------------------------

                const [peerBundle, myBundle] = await Promise.all([
                    deviceService.getBundle(
                        conversation.other_user.id
                    ),
                    deviceService.getBundle(
                        user.id
                    ),
                ]);

                encrypted =
                    await encryptForDevices({
                        conversationId: conversation.id,
                        plaintext: newPlaintext,
                        devices: [
                            ...(peerBundle?.devices ?? []),
                            ...(myBundle?.devices ?? []),
                        ],
                    });

            }

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

                                recipient_keys:
                                    recipientKeys,

                                envelopes:
                                    encrypted.envelopes ?? [],

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

            websocketService.sendEdit({
                conversationId: conversation.id,
                messageId,
                encrypted: {
                    ...encrypted,
                    recipient_keys: recipientKeys,
                    envelopes: encrypted.envelopes ?? [],
                },
            });

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

                const [peerBundle, myBundle] = await Promise.all([
                    deviceService.getBundle(
                        targetUser.id
                    ),
                    deviceService.getBundle(
                        user.id
                    ),
                ]);

                const encrypted =
                    await encryptForDevices({
                        conversationId: targetConversation.id,
                        plaintext,
                        devices: [
                            ...(peerBundle?.devices ?? []),
                            ...(myBundle?.devices ?? []),
                        ],
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
                    expires_at: saved.expires_at,
                    created_at: saved.created_at,
                    attachments: [],
                    recipient_keys: saved.recipient_keys ?? [],
                    envelopes: saved.envelopes ?? [],
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

        searchMessages,

        clearSearch,

        searchQuery,

        searchResults,

        searching,

        groupDetail,

        refreshGroupDetail,

    };
}
