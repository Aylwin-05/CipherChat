import { useState } from "react";

import useFriends from "../../hooks/useFriends";

import "./FriendsPage.css";

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

    return (

        <>

            <div className="friends-page">

                <h2>

                    Friends

                </h2>

                <input

                    type="text"

                    placeholder="Search email..."

                    value={query}

                    onChange={(e) =>

                        handleSearch(

                            e.target.value

                        )

                    }

                />

                {

                    searching && (

                        <p>

                            Searching...

                        </p>

                    )

                }

                <div className="friends-search-results">

                    {

                        searchResults.length === 0 &&

                        query.length > 0 &&

                        !searching && (

                            <p>

                                No users found.

                            </p>

                        )

                    }

                    {

                        searchResults.map((user) => (

                            <div

                                key={user.id}

                                className="friend-search-card"

                            >

                                <div>

                                    <strong>

                                        {user.display_name}

                                    </strong>

                                    <br />

                                    <small>

                                        {user.email}

                                    </small>

                                </div>

                                <button

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

                <hr />

                <h3>

                    Pending Requests

                </h3>

                {

                    pendingRequests.length === 0 && (

                        <p>

                            No pending requests.

                        </p>

                    )

                }

                <div className="pending-list">

                    {

                        pendingRequests.map((request) => (

                            <div

                                key={request.id}

                                className="pending-card"

                            >

                                <div>

                                    <strong>

                                        {

                                            request.sender?.display_name ??

                                            request.sender_id

                                        }

                                    </strong>

                                </div>

                                <div className="pending-actions">

                                    <button

                                        onClick={() =>

                                            acceptRequest(

                                                request.id

                                            )

                                        }

                                    >

                                        Accept

                                    </button>

                                    <button

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

                <hr />

                <h3>

                    Friends

                </h3>

                {

                    loading && (

                        <p>

                            Loading friends...

                        </p>

                    )

                }

                {

                    !loading &&

                    friends.length === 0 && (

                        <p>

                            You don't have any friends yet.

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

                                    className="friend-card"

                                >

                                    <div>

                                        <strong>

                                            {

                                                otherUser?.display_name ??

                                                "Unknown User"

                                            }

                                        </strong>

                                        <br />

                                        <small>

                                            {

                                                otherUser?.email ??

                                                ""

                                            }

                                        </small>

                                    </div>

                                    <div className="friend-actions">

                                        <button

                                            onClick={() =>

                                                onStartChat(friend)

                                            }

                                        >

                                            💬 Message

                                        </button>

                                        <button

                                            className="delete-btn"

                                            onClick={() =>

                                                handleRemove(friend)

                                            }

                                        >

                                            🗑 Remove

                                        </button>

                                    </div>

                                </div>

                            );

                        })

                    }

                </div>

            </div>

            {

                showDeleteModal && (

                    <div className="modal-overlay">

                        <div className="modal">

                            <h3>

                                Remove Friend

                            </h3>

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

                                    onClick={cancelDelete}

                                >

                                    Cancel

                                </button>

                                <button

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