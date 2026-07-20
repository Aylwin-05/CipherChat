import Sidebar from "../../components/layout/Sidebar";
import ConversationList from "../../components/chat/ConversationList";

import "./Dashboard.css";

export default function Dashboard() {

    return (

        <div className="dashboard">

            <Sidebar />

            <div className="dashboard-main">

                <header className="dashboard-header">

                    <h2>CipherChat</h2>

                </header>

                <div className="dashboard-content">

                    <div className="conversation-panel">

                        <h3>

                            Conversations

                        </h3>

                        <ConversationList />

                    </div>

                    <div className="chat-panel">

                        <h3>

                            Chat

                        </h3>

                        <div className="placeholder">

                            Select a conversation

                        </div>

                    </div>

                </div>

            </div>

        </div>

    );

}