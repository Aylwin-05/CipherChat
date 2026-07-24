import { useEffect, useState } from "react";

import friendService from "../services/friendService";

export default function useFriends() {

    const [friends, setFriends] =
        useState([]);

    const [pendingRequests, setPendingRequests] =
        useState([]);

    const [searchResults, setSearchResults] =
        useState([]);

    const [loading, setLoading] =
        useState(false);

    const [searching, setSearching] =
        useState(false);

    const [error, setError] =
        useState(null);

    // ======================================================
    // Initial Load
    // ======================================================

    useEffect(() => {

        loadData();

    }, []);

    async function loadData() {

        try {

            setLoading(true);

            const [

                friends,

                pending,

            ] = await Promise.all([

                friendService.getFriends(),

                friendService.getPendingRequests(),

            ]);

            setFriends(friends);

            setPendingRequests(pending);

        }

        catch (err) {

            console.error(err);

            setError(err);

        }

        finally {

            setLoading(false);

        }

    }

    // ======================================================
    // Search Users
    // ======================================================

    async function searchUsers(query) {

        if (!query.trim()) {

            setSearchResults([]);

            return;

        }

        try {

            setSearching(true);

            const users =
                await friendService.searchUsers(query);

            setSearchResults(users);

        }

        catch (err) {

            console.error(err);

        }

        finally {

            setSearching(false);

        }

    }

    // ======================================================
    // Send Friend Request
    // ======================================================

    async function sendFriendRequest(receiverId) {

        await friendService.sendFriendRequest(receiverId);

    }

    // ======================================================
    // Accept Request
    // ======================================================

    async function acceptRequest(friendshipId) {

        await friendService.acceptRequest(friendshipId);

        await loadData();

    }

    // ======================================================
    // Reject Request
    // ======================================================

    async function rejectRequest(friendshipId) {

        await friendService.rejectRequest(friendshipId);

        await loadData();

    }

    // ======================================================
    // Remove Friend
    // ======================================================

    async function removeFriend(friendshipId) {

        await friendService.removeFriend(friendshipId);

        await loadData();

    }

    return {

        friends,

        pendingRequests,

        searchResults,

        loading,

        searching,

        error,

        searchUsers,

        sendFriendRequest,

        acceptRequest,

        rejectRequest,

        removeFriend,

        refresh: loadData,

    };

}