import { Component } from "react";

export default class ErrorBoundary extends Component {

    constructor(props) {

        super(props);

        this.state = { hasError: false };

    }

    static getDerivedStateFromError() {

        return { hasError: true };

    }

    componentDidCatch(error, info) {

        console.error(
            "Unhandled UI error:",
            error,
            info,
        );

    }

    render() {

        if (this.state.hasError) {

            return (

                <div
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        minHeight: "100vh",
                        gap: "12px",
                        fontFamily: "sans-serif",
                    }}
                >
                    <h2>Something went wrong.</h2>
                    <p>Reload the page to continue.</p>
                    <button
                        onClick={() =>
                            window.location.reload()
                        }
                    >
                        Reload
                    </button>
                </div>
            );

        }

        return this.props.children;

    }

}