class WebSocketService {

    constructor() {

        this.socket = null;

        this.listeners = [];

        this.reconnectTimer = null;

        this.heartbeatTimer = null;

        this.shouldReconnect = false;

        this.reconnectAttempts = 0;

        this.lastAliveAt = null;

        this.token = null;

        // Reconnect policy: 1s, 2s, 4s ... capped at 30s
        this.maxReconnectDelay = 30_000;

        // Heartbeat every 20s; declare dead if silent for 60s
        this.heartbeatInterval = 20_000;

        this.staleThreshold = 60_000;

    }

    // ======================================================
    // CONNECT
    // ======================================================

    connect(
        token,
    ) {

        this.token = token;

        this.shouldReconnect = true;

        this.reconnectAttempts = 0;

        this._openSocket();

    }

    _openSocket() {

        this._closeSocket();

        this.shouldReconnect = true;

        const configured =
            import.meta.env.VITE_WS_URL;

        const url = configured
            ? `${configured}/ws/me`
            : `${window.location.protocol === "https:"
                ? "wss"
                : "ws"
            }://${window.location.host}/ws/me`;

        const socket =
            new WebSocket(
                url,
                ["cipherchat." + this.token]
            );

        // Supersede guard: any socket no longer owned by the
        // service (a newer connect replaced it, or an explicit
        // disconnect happened) must not schedule reconnects,
        // start heartbeats or dispatch events.
        this.socket = socket;

        this.lastAliveAt = Date.now();

        socket.onopen = () => {

            if (this.socket !== socket) {

                return;

            }

            console.log(
                "WebSocket connected"
            );

            this.reconnectAttempts = 0;

            this._startHeartbeat();

        };

        socket.onmessage = (event) => {

            if (this.socket !== socket) {

                return;

            }

            this.lastAliveAt = Date.now();

            try {

                const data =
                    JSON.parse(event.data);

                // Show backend websocket errors
                if (data.event === "error") {

                    console.error(
                        "WebSocket:",
                        data.message,
                    );

                    return;

                }

                this.listeners.forEach(
                    listener => listener(data)
                );

            }

            catch (error) {

                console.error(
                    "Invalid websocket payload",
                    error,
                );

            }

        };

        socket.onclose = () => {

            if (this.socket !== socket) {

                // Superseded — a newer socket owns the slot
                // (or an explicit disconnect happened).
                return;

            }

            this.socket = null;

            this._stopHeartbeat();

            if (this.shouldReconnect) {

                this._scheduleReconnect();

            }

        };

        socket.onerror = (error) => {

            if (this.socket !== socket) {

                return;

            }

            console.error(
                "WebSocket error",
                error,
            );

        };

    }

    // ======================================================
    // Close the current socket WITHOUT touching listeners.
    //
    // Listeners survive reconnects on purpose: wiping them
    // here used to silently kill real-time updates — the
    // socket came back, but nothing was left to dispatch
    // the broadcast to the UI.
    // ======================================================

    _closeSocket() {

        const socket = this.socket;

        if (!socket) return;

        if (socket.readyState === WebSocket.CONNECTING) {

            // Closing a connecting socket makes the browser
            // log "WebSocket is closed before the connection
            // is established". Drop the handlers instead; the
            // connection resolves (or fails) without callbacks.
            this.socket = null;

            socket.onopen = null;
            socket.onmessage = null;
            socket.onerror = null;
            socket.onclose = null;

            return;

        }

        // Keep the slot owned by this socket: its own onclose
        // handler will null it, stop the heartbeat, and (when
        // shouldReconnect is still set) schedule the reconnect.
        socket.close();

    }

    // ======================================================
    // RECONNECT / HEARTBEAT
    // ======================================================

    _scheduleReconnect() {

        if (!this.shouldReconnect) return;

        const delay =
            Math.min(
                1000 * (2 ** this.reconnectAttempts),
                this.maxReconnectDelay
            );

        this.reconnectAttempts += 1;

        console.log(
            `WebSocket reconnect in ${delay}ms`
        );

        this.reconnectTimer =
            setTimeout(
                () => this._openSocket(),
                delay,
            );

    }

    _startHeartbeat() {

        this._stopHeartbeat();

        this.heartbeatTimer =
            setInterval(
                () => this._checkAlive(),
                this.heartbeatInterval,
            );

    }

    _stopHeartbeat() {

        if (this.heartbeatTimer) {

            clearInterval(this.heartbeatTimer);

            this.heartbeatTimer = null;

        }

    }

    _checkAlive() {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        const now = Date.now();

        if (now - this.lastAliveAt > this.staleThreshold) {

            console.warn(
                "WebSocket heartbeat timeout, reconnecting"
            );

            // Closing triggers onclose -> reconnect
            this._closeSocket();

            return;

        }

        try {

            this.socket.send(
                JSON.stringify({
                    event: "ping",
                })
            );

        }

        catch (error) {

            console.warn(
                "WebSocket send failed, reconnecting",
                error,
            );

            this._closeSocket();

        }

    }

    // ======================================================
    // SEND MESSAGE
    // ======================================================

    sendMessage(message) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "message",

                ...message,

            })

        );

    }

    // ======================================================
    // TYPING
    // ======================================================

    sendTyping(conversationId) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "typing",

                conversation_id: conversationId,

            })

        );

    }

    // ======================================================
    // STOP TYPING
    // ======================================================

    stopTyping(conversationId) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "stop_typing",

                conversation_id: conversationId,

            })

        );

    }

    // ======================================================
    // READ RECEIPT
    // ======================================================

    sendRead(
        conversationId,
        messageId,
    ) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "read",

                conversation_id: conversationId,

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // DELIVERED RECEIPT
    // ======================================================

    sendDelivered(
        conversationId,
        messageId,
    ) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "delivered",

                conversation_id: conversationId,

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // EDIT
    //
    // The edited content arrives already encrypted (Signal
    // ratchet); the server swaps the payload fields and the
    // plaintext never touches it.
    // ======================================================

    sendEdit({
        conversationId,
        messageId,
        encrypted,
    }) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "edit",

                conversation_id: conversationId,

                message_id: messageId,

                ciphertext:
                    encrypted.ciphertext,

                encrypted_key_sender:
                    encrypted.encrypted_key_sender,

                encrypted_key_receiver:
                    encrypted.encrypted_key_receiver,

                nonce:
                    encrypted.nonce,

                recipient_keys:
                    encrypted.recipient_keys || [],

            })

        );

    }

    // ======================================================
    // DELETE
    // ======================================================

    sendDelete(
        conversationId,
        messageId,
    ) {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "delete",

                conversation_id: conversationId,

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // PING
    // ======================================================

    ping() {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "ping",

            })

        );

    }

    // ======================================================
    // LISTENERS
    // ======================================================

    onMessage(listener) {

        this.listeners.push(listener);

    }

    removeListener(listener) {

        this.listeners = this.listeners.filter(
            existing => existing !== listener
        );

    }

    removeListeners() {

        this.listeners = [];

    }

    // ======================================================
    // DISCONNECT
    // ======================================================

    disconnect() {

        this.shouldReconnect = false;

        this._stopHeartbeat();

        if (this.reconnectTimer) {

            clearTimeout(this.reconnectTimer);

            this.reconnectTimer = null;

        }

        this._closeSocket();

        this.removeListeners();

    }

}

export default new WebSocketService();