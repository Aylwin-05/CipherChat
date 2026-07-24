class WebSocketService {

    constructor() {

        this.socket = null;

        this.listeners = [];

    }

    // ======================================================
    // CONNECT
    // ======================================================

    connect(
        conversationId,
        token,
    ) {

        this.disconnect();

        const url =
            `ws://127.0.0.1:8000/ws/${conversationId}?token=${token}`;

        this.socket =
            new WebSocket(url);

        this.socket.onopen = () => {

            console.log(
                "WebSocket connected"
            );

        };

        this.socket.onmessage = (event) => {

            const data =
                JSON.parse(event.data);

            this.listeners.forEach(
                listener => listener(data)
            );

        };

        this.socket.onclose = () => {

            console.log(
                "WebSocket disconnected"
            );

        };

        this.socket.onerror = (error) => {

            console.error(
                "WebSocket error",
                error
            );

        };

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

    sendRead(messageId) {

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

    sendDelivered(messageId) {

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
    // LISTENER
    // ======================================================

    onMessage(listener) {

        this.listeners = [

            listener,

        ];

    }

    // ======================================================
    // DISCONNECT
    // ======================================================

    disconnect() {

        if (this.socket) {

            this.socket.close();

            this.socket = null;

        }

    }

}

export default new WebSocketService();