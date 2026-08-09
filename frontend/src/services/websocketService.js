class WebSocketService {

    constructor() {

        this.socket = null;

        this.listeners = [];

        this.reconnectTimer = null;

        this.heartbeatTimer = null;

        this.shouldReconnect = false;

        this.reconnectAttempts = 0;

        this.lastAliveAt = null;

        this.conversationId = null;

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
        conversationId,
        token,
    ) {

        this.conversationId = conversationId;

        this.token = token;

        this.shouldReconnect = true;

        this.reconnectAttempts = 0;

        this._openSocket();

    }

    _openSocket() {

        this.disconnect();

        this.shouldReconnect = true;

        const configured =
            import.meta.env.VITE_WS_URL;

        const url = configured
            ? `${configured}/ws/${this.conversationId}`
            : `${window.location.protocol === "https:"
                ? "wss"
                : "ws"
            }://${window.location.host}/ws/${this.conversationId}`;

        this.socket =
            new WebSocket(
                url,
                ["cipherchat." + this.token]
            );

        this.lastAliveAt = Date.now();

        this.socket.onopen = () => {

            console.log(
                "WebSocket connected"
            );

            this.reconnectAttempts = 0;

            this._startHeartbeat();

        };

        this.socket.onmessage = (event) => {

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

        this.socket.onclose = () => {

            this._stopHeartbeat();

            this.socket = null;

            if (this.shouldReconnect) {

                this._scheduleReconnect();

            }

        };

        this.socket.onerror = (error) => {

            console.error(
                "WebSocket error",
                error,
            );

        };

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
            this.socket.close();

            return;

        }

        this.socket.send(
            JSON.stringify({
                event: "ping",
            })
        );

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

    sendTyping() {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "typing",

            })

        );

    }

    // ======================================================
    // STOP TYPING
    // ======================================================

    stopTyping() {

        if (
            !this.socket ||
            this.socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        this.socket.send(

            JSON.stringify({

                event: "stop_typing",

            })

        );

    }

    // ======================================================
    // READ RECEIPT
    // ======================================================

    sendRead(
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

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // DELIVERED RECEIPT
    // ======================================================

    sendDelivered(
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

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // EDIT
    // ======================================================

    sendEdit(
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

                event: "edit",

                message_id: messageId,

            })

        );

    }

    // ======================================================
    // DELETE
    // ======================================================

    sendDelete(
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

        if (this.socket) {

            this.socket.close();

            this.socket = null;

        }

        this.removeListeners();

    }

}

export default new WebSocketService();