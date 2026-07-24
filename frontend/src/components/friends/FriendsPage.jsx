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

    } = useFriends();

    const [

        query,

        setQuery,

    ] = useState("");

    //--------------------------------------------------

    async function handleSearch(value) {

        setQuery(value);

        await searchUsers(value);

    }

    //--------------------------------------------------

    return (

        <div className="friends-page">

            <h2>

                Friends

            </h2>

            <input

                type="text"

                placeholder="Search username..."

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

                                @{user.username}

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

                                {request.sender?.display_name ??
                                    request.sender_id}

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

                friends.map((friend) => (

                    <div
                        key={friend.id}
                        className="friend-card"
                    >

                        <div>

                            <strong>

                                {

                                    friend.friend?.display_name ??

                                    friend.receiver?.display_name ??

                                    friend.sender?.display_name ??

                                    "Unknown User"

                                }

                            </strong>

                        </div>

                        <button
                            onClick={() =>
                                onStartChat(friend)
                            }
                        >
                            Message
                        </button>

                    </div>

                ))

            }

        </div>

    </div>

    );

}