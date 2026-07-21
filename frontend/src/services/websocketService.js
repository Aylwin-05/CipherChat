class WebSocketService {

    constructor() {

        this.socket = null;
        this.listeners = [];

    }

    connect(
        conversationId,
        token,
    ) {

        if (
            this.socket &&
            this.socket.readyState === WebSocket.OPEN
        ) {
            this.socket.close();
        }

        const url =
            `ws://127.0.0.1:8000/ws/${conversationId}?token=${token}`;

        this.socket = new WebSocket(url);

        this.socket.onmessage = (event) => {

            const data = JSON.parse(event.data);

            this.listeners.forEach((listener) =>
                listener(data)
            );

        };

        this.socket.onclose = () => {

            console.log("WebSocket disconnected");

        };

        this.socket.onerror = (error) => {

            console.error(error);

        };

    }

    sendMessage(content) {

        if (!this.socket) return;

        this.socket.send(
            JSON.stringify({
                event: "message",
                content,
            })
        );

    }

    sendTyping() {

        if (!this.socket) return;

        this.socket.send(
            JSON.stringify({
                event: "typing",
            })
        );

    }

    stopTyping() {

        if (!this.socket) return;

        this.socket.send(
            JSON.stringify({
                event: "stop_typing",
            })
        );

    }

    onMessage(listener) {

        this.listeners = [listener];

    }

    disconnect() {

        if (this.socket) {

            this.socket.close();

            this.socket = null;

        }

    }

}

export default new WebSocketService();