import { useState } from "react";

import useFriends from "../../hooks/useFriends";

import { avatarGradient, initials } from "../../utils/avatar";

import UserAvatar from "../UserAvatar";

import "./FriendsPage.css";

function SearchIcon() {
    return (
        <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
        >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
        </svg>
    );
}

export default function FriendsPage({

    onStartChat,

}) {

    const {

        friends,

        pendingRequests,

        searchResults,

        loading,

        searching,

        searchUsers,

        sendFriendRequest,

        acceptRequest,

        rejectRequest,

        removeFriend,

    } = useFriends();

    const [

        query,

        setQuery,

    ] = useState("");

    const [

        showDeleteModal,

        setShowDeleteModal,

    ] = useState(false);

    const [

        friendToDelete,

        setFriendToDelete,

    ] = useState(null);

    //--------------------------------------------------

    async function handleSearch(value) {

        setQuery(value);

        await searchUsers(value);

    }

    //--------------------------------------------------

    function handleRemove(friend) {

        setFriendToDelete(friend);

        setShowDeleteModal(true);

    }

    //--------------------------------------------------

    async function confirmDelete() {

        if (!friendToDelete) {

            return;

        }

        await removeFriend(friendToDelete.id);

        setFriendToDelete(null);

        setShowDeleteModal(false);

    }

    //--------------------------------------------------

    function cancelDelete() {

        setFriendToDelete(null);

        setShowDeleteModal(false);

    }

    //--------------------------------------------------

    function friendDisplayName(friend) {

        return friend.sender?.id === friend.receiver_id

            ? (friend.receiver?.display_name ?? "Unknown User")

            : (friend.sender?.display_name ?? "Unknown User");

    }

    return (

        <>

            <div className="friends-page">

                <div className="friends-header">

                    <h2>Friends</h2>

                    <p>
                        Find people, send friend requests and
                        start encrypted chats.
                    </p>

                </div>

                <div className="field friends-search">

                    <SearchIcon />

                    <input

                        type="text"

                        placeholder="Search by email..."

                        value={query}

                        onChange={(e) =>

                            handleSearch(

                                e.target.value

                            )

                        }

                    />

                </div>

                {/* ------- search results ------- */}

                <div className="friends-search-results">

                    {

                        searching && (

                            <div className="friends-hint">

                                <span className="spinner spinner-sm" />

                                Searching…

                            </div>

                        )

                    }

                    {

                        searchResults.length === 0 &&

                        query.length > 0 &&

                        !searching && (

                            <div className="friends-hint">

                                No users found for{" "}
                                <strong>"{query}"</strong>.

                            </div>

                        )

                    }

                    {

                        searchResults.map((user) => (

                            <div

                                key={user.id}

                                className="f-card search"

                            >

                                <div

                                    className="f-avatar"

                                    style={{
                                        background: avatarGradient(
                                            user.display_name
                                        ),
                                    }}

                                >

                                    {initials(
                                        user.display_name
                                    )}

                                </div>

                                <div className="f-meta">

                                    <strong>

                                        {user.display_name}

                                    </strong>

                                    <small>

                                        {user.email}

                                    </small>

                                </div>

                                <button

                                    type="button"

                                    className="btn-primary btn-sm"

                                    onClick={() =>

                                        sendFriendRequest(

                                            user.id

                                        )

                                    }

                                >

                                    Add Friend

                                </button>

                            </div>

                        ))

                    }

                </div>

                {/* ------- pending requests ------- */}

                <section className="friends-section">

                    <div className="friends-section-head">

                        <h3>Pending Requests</h3>

                        {pendingRequests.length > 0 && (

                            <span className="section-count">

                                {pendingRequests.length}

                            </span>

                        )}

                    </div>

                    {

                        pendingRequests.length === 0 && (

                            <p className="friends-hint">

                                No pending requests.

                            </p>

                        )

                    }

                    <div className="pending-list">

                        {

                            pendingRequests.map((request) => (

                                <div

                                    key={request.id}

                                    className="f-card"

                                >

                                    <div

                                        className="f-avatar"

                                        style={{
                                            background: avatarGradient(
                                                request.sender?.display_name
                                            ),
                                        }}

                                    >

                                        {initials(
                                            request.sender?.display_name ?? "?"
                                        )}

                                    </div>

                                    <div className="f-meta">

                                        <strong>

                                            {

                                                request.sender?.display_name ??

                                                request.sender_id

                                            }

                                        </strong>

                                        <small>

                                            Wants to chat with you

                                        </small>

                                    </div>

                                    <div className="f-actions">

                                        <button

                                            type="button"

                                            className="btn-primary btn-sm"

                                            onClick={() =>

                                                acceptRequest(

                                                    request.id

                                                )

                                            }

                                        >

                                            Accept

                                        </button>

                                        <button

                                            type="button"

                                            className="btn-ghost btn-sm"

                                            onClick={() =>

                                                rejectRequest(

                                                    request.id

                                                )

                                            }

                                        >

                                            Reject

                                        </button>

                                    </div>

                                </div>

                            ))

                        }

                    </div>

                </section>

                {/* ------- friends list ------- */}

                <section className="friends-section">

                    <div className="friends-section-head">

                        <h3>Friends</h3>

                        <span className="section-count">

                            {friends.length}

                        </span>

                    </div>

                    {

                        loading && (

                            <div className="friends-hint">

                                Loading friends…

                            </div>

                        )

                    }

                    {

                        !loading &&

                        friends.length === 0 && (

                            <p className="friends-hint">

                                You don't have any friends yet.
                                Search by email above to add
                                your first one.

                            </p>

                        )

                    }

                    <div className="friends-list">

                        {

                            friends.map((friend) => {

                                const otherUser =

                                    friend.sender?.id === friend.receiver_id

                                        ? friend.receiver

                                        : friend.sender;

                                return (

                                    <div

                                        key={friend.id}

                                        className="f-card"

                                    >

                                        <UserAvatar

                                            user={otherUser}

                                            className="f-avatar"

                                        />

                                        <div className="f-meta">

                                            <strong>

                                                {

                                                    otherUser?.display_name ??

                                                    "Unknown User"

                                                }

                                            </strong>

                                            <small>

                                                {

                                                    otherUser?.email ??

                                                    ""

                                                }

                                            </small>

                                        </div>

                                        <div className="f-actions">

                                            <button

                                                type="button"

                                                className="btn-ghost btn-sm"

                                                onClick={() =>

                                                    onStartChat(friend)

                                                }

                                            >

                                                <svg
                                                    width="15"
                                                    height="15"
                                                    viewBox="0 0 24 24"
                                                    fill="none"
                                                    stroke="currentColor"
                                                    strokeWidth="2"
                                                    strokeLinecap="round"
                                                    strokeLinejoin="round"
                                                >
                                                    <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
                                                </svg>

                                                Message

                                            </button>

                                            <button

                                                type="button"

                                                className="btn-danger btn-sm"

                                                onClick={() =>

                                                    handleRemove(friend)

                                                }

                                            >

                                                Remove

                                            </button>

                                        </div>

                                    </div>

                                );

                            })

                        }

                    </div>

                </section>

            </div>

            {

                showDeleteModal && (

                    <div className="modal-overlay">

                        <div className="modal-card">

                            <h3>Remove Friend</h3>

                            <p>

                                Are you sure you want to remove

                                <strong>

                                    {" "}

                                    {

                                        friendToDelete?.sender?.id === friendToDelete?.receiver_id

                                            ? friendToDelete?.receiver?.display_name

                                            : friendToDelete?.sender?.display_name

                                    }

                                </strong>

                                {" "}from your friends?

                            </p>

                            <div className="modal-actions">

                                <button

                                    type="button"

                                    className="btn-ghost"

                                    onClick={cancelDelete}

                                >

                                    Cancel

                                </button>

                                <button

                                    type="button"

                                    className="btn-danger"

                                    onClick={confirmDelete}

                                >

                                    Remove

                                </button>

                            </div>

                        </div>

                    </div>

                )

            }

        </>

    );

}