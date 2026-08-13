import {
    useEffect,
    useState,
} from "react";
import toast from "react-hot-toast";
import { useAuth } from "../../context/AuthContext";

import UserAvatar from "../UserAvatar";

import friendService from "../../services/friendService";
import conversationService from "../../services/conversationService";

import "./GroupModal.css";
import "./GroupInfoModal.css";

export default function GroupInfoModal({
    conversation,
    groupDetail,
    onClose,
    onUpdated,
    onLeave,
}) {

    const { user } = useAuth();

    const [friends, setFriends] =
        useState([]);

    const [showPicker, setShowPicker] =
        useState(false);

    const [selected, setSelected] =
        useState([]);

    const [busy, setBusy] =
        useState(false);

    const participants =
        groupDetail?.participants ?? [];

    const isAdmin =
        participants.some(
            participant =>
                participant.user_id ===
                    user?.id &&
                participant.is_admin
        );

    useEffect(() => {

        if (!showPicker) return;

        let active = true;

        friendService.getFriends()
            .then(data => {

                if (active) setFriends(data);

            })
            .catch(error => {

                console.error(
                    "Failed to load friends",
                    error
                );

            });

        return () => {
            active = false;
        };

    }, [showPicker]);

    async function handleAddMembers() {

        if (selected.length === 0) return;

        setBusy(true);

        try {

            await conversationService.addGroupMembers(
                conversation.id,
                selected.map(member => member.id)
            );

            toast.success(
                "Members added. "
                + "Their sessions were re-encrypted."
            );

            setSelected([]);

            setShowPicker(false);

            onUpdated?.();

        }
        catch (error) {

            toast.error(
                error.response?.data?.detail ??
                "Unable to add members."
            );

        }
        finally {

            setBusy(false);

        }

    }

    async function handleLeave() {

        setBusy(true);

        try {

            await conversationService.leaveGroup(
                conversation.id
            );

            toast.success(
                "You left the group."
            );

            onLeave?.();

            onClose();

        }
        catch (error) {

            toast.error(
                error.response?.data?.detail ??
                "Unable to leave the group."
            );

        }
        finally {

            setBusy(false);

        }

    }

    const friendList = Array.isArray(friends)
        ? friends
        : [];

    const friendsToAdd =
        friendList.filter(friend => {

            const other =
                friend.sender?.id ===
                    friend.receiver_id
                    ? friend.receiver
                    : friend.sender;

            return !participants.some(
                participant =>
                    participant.user_id === other?.id
            );

        });

    return (

        <div className="modal-backdrop" onMouseDown={onClose}>

            <div
                className="group-info-modal"
                onMouseDown={e => e.stopPropagation()}
            >

                <div className="modal-head">

                    <button
                        type="button"
                        className="modal-close"
                        aria-label="Close"
                        onClick={onClose}
                    >
                        ✕
                    </button>

                    <h3>Group info</h3>

                </div>

                <div className="group-info-body">

                    <div className="group-info-hero">

                        <div className="group-info-avatar">
                            {(
                                conversation?.name ??
                                groupDetail?.name ??
                                "?"
                            ).slice(0, 1).toUpperCase()}
                        </div>

                        <strong className="group-info-name">
                            {conversation?.name ??
                                groupDetail?.name}
                        </strong>

                        <span className="group-info-count">
                            {participants.length} members
                        </span>

                    </div>

                    <div className="group-info-section">

                        <div className="group-info-section-head">

                            <span className="group-info-section-title">
                                Members
                            </span>

                            {isAdmin && (
                                <button
                                    type="button"
                                    className="group-info-add-btn"
                                    onClick={() =>
                                        setShowPicker(
                                            previous =>
                                                !previous
                                        )
                                    }
                                >
                                    {showPicker
                                        ? "Cancel"
                                        : "+ Add members"}
                                </button>
                            )}

                        </div>

                        {showPicker && isAdmin && (
                            <div className="group-add-picker">

                                {friendsToAdd.length ===
                                0 ? (
                                    <div className="group-empty-state">
                                        No friends left to
                                        add.
                                    </div>
                                ) : (
                                    friendsToAdd.map(
                                        friend => {

                                            const other =
                                                friend.sender
                                                    ?.id ===
                                                    friend.receiver_id
                                                    ? friend
                                                          .receiver
                                                    : friend
                                                          .sender;

                                            const checked =
                                                selected.some(
                                                    item =>
                                                        item.id ===
                                                        other?.id
                                                );

                                            return (

                                                <button
                                                    key={other?.id}
                                                    type="button"
                                                    className={
                                                        checked
                                                            ? "group-add-item selected"
                                                            : "group-add-item"
                                                    }
                                                    onClick={() => {

                                                        if (!other) return;

                                                        setSelected(
                                                            previous =>
                                                                previous.some(
                                                                    item =>
                                                                        item.id ===
                                                                        other.id
                                                                )
                                                                    ? previous.filter(
                                                                          item =>
                                                                              item.id !==
                                                                              other.id
                                                                      )
                                                                    : [
                                                                          ...previous,
                                                                          other,
                                                                      ]
                                                        );

                                                    }}
                                                >

                                                    <UserAvatar
                                                        user={other}
                                                        className="group-friend-avatar"
                                                    />

                                                    <span className="group-friend-name">
                                                        {other?.display_name ??
                                                            other?.username ??
                                                            "Unknown"}
                                                    </span>

                                                    {checked && (
                                                        <span className="group-friend-check">
                                                            ✓
                                                        </span>
                                                    )}

                                                </button>

                                            );

                                        }
                                    )
                                )}

                                <button
                                    type="button"
                                    className="btn-primary group-add-confirm"
                                    disabled={
                                        busy ||
                                        selected.length === 0
                                    }
                                    onClick={handleAddMembers}
                                >
                                    {busy
                                        ? "Adding…"
                                        : `Add ${selected.length}`}
                                </button>

                            </div>
                        )}

                        <div className="group-members-list">

                            {participants.map(
                                participant => {

                                    const member =
                                        participant.user ??
                                        {};

                                    const isMe =
                                        participant.user_id ===
                                        user?.id;

                                    return (

                                        <div
                                            key={
                                                participant.user_id
                                            }
                                            className="group-member-item"
                                        >

                                            <UserAvatar
                                                user={member}
                                                className="group-member-avatar"
                                            />

                                            <div className="group-member-meta">

                                                <strong>
                                                    {member.display_name ??
                                                        member.username ??
                                                        "Unknown"}
                                                </strong>

                                                {isMe && (
                                                    <span className="group-member-me">
                                                        (you)
                                                    </span>
                                                )}

                                            </div>

                                            {participant.is_admin && (
                                                <span className="group-admin-badge">
                                                    admin
                                                </span>
                                            )}

                                        </div>

                                    );

                                }
                            )}

                        </div>

                    </div>

                </div>

                <div className="group-info-footer">

                    <button
                        type="button"
                        className="btn-danger-ghost"
                        disabled={busy}
                        onClick={handleLeave}
                    >
                        Leave group
                    </button>

                </div>

            </div>

        </div>

    );

}