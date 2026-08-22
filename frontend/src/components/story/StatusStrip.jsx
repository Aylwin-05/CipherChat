import { useEffect, useState } from "react";

import "./StatusStrip.css";

import { useAuth } from "../../context/AuthContext";
import { useChatSocket } from "../../context/ChatSocketContext";
import StoryComposer from "./StoryComposer";
import StoryViewer from "./StoryViewer";

// ==========================================================
// StatusStrip — WhatsApp-style 24h status updates
//
// Horizontal row of story rings above the conversation list:
// "My status" first (with a + button when empty), then each
// friend who posted something in the last 24h.
// ==========================================================

export default function StatusStrip() {

    const { user } = useAuth();

    const {
        stories,
        refreshStories,
    } = useChatSocket();

    const [composerOpen, setComposerOpen] =
        useState(false);

    const [viewerGroup, setViewerGroup] =
        useState(null);

    // Load the feed once on mount (and after reconnect
    // events handled by the provider).
    useEffect(() => {

        void refreshStories();

    }, []);

    if (!user) return null;

    const myGroup =
        stories.find(
            group => group.user_id === user.id
        );

    const friendGroups =
        stories.filter(
            group => group.user_id !== user.id
        );

    const hasMyStories =
        (myGroup?.stories?.length ?? 0) > 0;

    return (
        <>
            <div className="status-strip">

                {/* My status */}
                <button
                    type="button"
                    className={
                        hasMyStories
                            ? "status-ring mine has-stories"
                            : "status-ring mine"
                    }
                    onClick={() => {

                        if (hasMyStories) {

                            setViewerGroup(myGroup);

                        }
                        else {

                            setComposerOpen(true);

                        }

                    }}
                    title="My status"
                >
                    <span className="status-ring-avatar">
                        {user.avatar_url
                            ? (
                                <img
                                    src={user.avatar_url}
                                    alt="My status"
                                />
                            )
                            : user.display_name?.[0]?.toUpperCase()
                        }
                        <span className="status-ring-add">
                            +
                        </span>
                    </span>
                    <span className="status-ring-name">
                        My status
                    </span>
                </button>

                {/* Friends' stories */}
                {friendGroups.map(group => (
                    <button
                        key={group.user_id}
                        type="button"
                        className={
                            group.stories.some(s => !s.viewed)
                                ? "status-ring has-unviewed"
                                : "status-ring"
                        }
                        onClick={() =>
                            setViewerGroup(group)
                        }
                        title={
                            group.owner?.display_name ??
                            "Status"
                        }
                    >
                        <span className="status-ring-avatar">
                            {group.owner?.avatar_url
                                ? (
                                    <img
                                        src={group.owner.avatar_url}
                                        alt=""
                                    />
                                )
                                : group.owner?.display_name?.[0]?.toUpperCase()
                            }
                        </span>
                        <span className="status-ring-name">
                            {group.owner?.display_name}
                        </span>
                    </button>
                ))}

            </div>

            {composerOpen && (
                <StoryComposer
                    onClose={() =>
                        setComposerOpen(false)
                    }
                    onPosted={(group) => {

                        setComposerOpen(false);

                        setViewerGroup(group);

                    }}
                />
            )}

            {viewerGroup && (
                <StoryViewer
                    group={viewerGroup}
                    onClose={() =>
                        setViewerGroup(null)
                    }
                    onGroupUpdated={setViewerGroup}
                />
            )}
        </>
    );

}