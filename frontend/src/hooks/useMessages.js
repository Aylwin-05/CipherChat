import {
    useEffect,
    useState,
} from "react";

import { useAuth } from "../context/AuthContext";

import messageService from "../services/messageService";
import websocketService from "../services/websocketService";
import keyService from "../services/keyService";

import {
    encryptMessage,
    decryptMessage,
    importPrivateKey,
    importPublicKey,
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

        initialize();

        return () => {

            websocketService.disconnect();

        };

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
            // Import my private key
            //--------------------------------------------------

            const privateKey =
                await importPrivateKey(
                    getPrivateKey()
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
                                    await decryptMessage(

                                        message.ciphertext,

                                        message.encrypted_key,

                                        message.nonce,

                                        privateKey,

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

                                const privateKey =
                                    await importPrivateKey(
                                        getPrivateKey()
                                    );

                                const plaintext =
                                    await decryptMessage(

                                        event.ciphertext,

                                        event.encrypted_key,

                                        event.nonce,

                                        privateKey,

                                    );

                                const message = {

                                    ...event,

                                    content: plaintext,

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
    ) {

        try {

            //------------------------------------------
            // Fetch recipient public key
            //------------------------------------------

            const response =
                await keyService.getPublicKey(
                    conversation.other_user.id
                );

            const recipientPublicKey =
                await importPublicKey(
                    response.public_key
                );

            //------------------------------------------
            // Encrypt locally
            //------------------------------------------

            const encrypted =
                await encryptMessage(
                    plaintext,
                    recipientPublicKey,
                );

            //------------------------------------------
            // Save encrypted payload via REST
            //------------------------------------------

            const saved =
                await messageService.sendMessage(

                    conversation.id,

                    encrypted,

                );

            //------------------------------------------
            // Show instantly for sender
            //------------------------------------------

            const localMessage = {

                ...saved,

                content: plaintext,

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

                encrypted_key:
                    saved.encrypted_key,

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

        typingUsers,

        loading,

        error,

        sendMessage,

        typing,

        stopTyping,

    };

}