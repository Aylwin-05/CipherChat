import {
    createContext,
    useContext,
    useEffect,
    useRef,
    useState,
} from "react";

import { useAuth } from "./AuthContext";
import { useChatSocket } from "./ChatSocketContext";

import websocketService from "../services/websocketService";

import IncomingCallModal from "../components/call/IncomingCallModal";
import ActiveCallOverlay from "../components/call/ActiveCallOverlay";

const CallContext = createContext(null);

const ICE_SERVERS = [
    {
        urls: "stun:stun.l.google.com:19302",
    },
];

function emptyCall() {

    return {

        conversationId: null,

        callId: null,

        callType: "voice",

        peerId: null,

        peerName: "Unknown",

        status: "idle", // ringing | connecting | in-call | ended

    };

}

export function CallProvider({ children }) {

    const { user } = useAuth();

    const {
        conversations,
        subscribe,
    } = useChatSocket();

    const userRef = useRef(user);

    const [incomingCall, setIncomingCall] =
        useState(null);

    const [call, setCall] =
        useState(emptyCall());

    const [localStream, setLocalStream] =
        useState(null);

    const [remoteStream, setRemoteStream] =
        useState(null);

    const [muted, setMuted] =
        useState(false);

    const [videoEnabled, setVideoEnabled] =
        useState(true);

    const peerConnectionRef = useRef(null);

    const callRef = useRef(call);

    const incomingRef = useRef(incomingCall);

    useEffect(() => {

        userRef.current = user;

    }, [user]);

    useEffect(() => {

        callRef.current = call;

    }, [call]);

    useEffect(() => {

        incomingRef.current = incomingCall;

    }, [incomingCall]);

    //=====================================================
    // Media + peer connection teardown
    //=====================================================

    async function cleanup() {

        const peer =
            peerConnectionRef.current;

        if (peer) {

            try {
                peer.onicecandidate = null;
                peer.ontrack = null;
                peer.onconnectionstatechange = null;
                peer.close();
            }
            catch (e) {
                console.error(e);
            }

            peerConnectionRef.current = null;

        }

        if (localStream) {

            for (const track of localStream.getTracks()) {

                track.stop();

            }

        }

        setLocalStream(null);

        if (remoteStream) {

            for (const track of remoteStream.getTracks()) {

                track.stop();

            }

        }

        setRemoteStream(null);

        setMuted(false);

        setVideoEnabled(true);

        callRef.current = emptyCall();

        setCall(emptyCall());

        setIncomingCall(null);

        incomingRef.current = null;

    }

    //=====================================================
    // Find the peer's display name for a private
    // conversation (used for incoming calls).
    //=====================================================

    function peerNameFor(conversationId, fallbackId) {

        const conv = conversations.find(
            c => c.id === conversationId
        );

        return (
            conv?.other_user?.display_name ??
            fallbackId ??
            "Unknown"
        );

    }

    //=====================================================
    // ICE candidate -> signaling relay
    //=====================================================

    function handleIceCandidate(event) {

        const current = callRef.current;

        if (
            !current.callId ||
            !current.peerId ||
            !event.candidate
        ) {
            return;
        }

        websocketService.sendCallEvent(
            "call_ice",
            current.conversationId,
            current.callId,
            {
                to: current.peerId,
                candidate: event.candidate.toJSON(),
            }
        );

    }

    //=====================================================
    // WebRTC peer setup shared by caller + callee
    //=====================================================

    async function setupPeer(stream, onTrack, onStateChange) {

        const peer = new RTCPeerConnection({
            iceServers: ICE_SERVERS,
        });

        peer.onicecandidate =
            handleIceCandidate;

        peer.ontrack =
            onTrack;

        peer.onconnectionstatechange =
            onStateChange;

        peerConnectionRef.current = peer;

        if (stream) {

            for (const track of stream.getTracks()) {

                peer.addTrack(track, stream);

            }

        }

        return peer;

    }

    //=====================================================
    // Start an outgoing voice/video call
    //=====================================================

    async function startCall(
        conversationId,
        callType,
        peerId,
        peerName,
    ) {

        if (callRef.current.callId) return;

        try {

            const stream =
                await navigator.mediaDevices.getUserMedia({
                    audio: true,
                    video: callType === "video",
                });

            setLocalStream(stream);

            setVideoEnabled(callType === "video");

            const callId = crypto.randomUUID();

            callRef.current = {
                conversationId,
                callId,
                callType,
                peerId,
                peerName,
                status: "ringing",
            };

            setCall(callRef.current);

            const peer =
                await setupPeer(
                    stream,
                    (event) => {
                        setRemoteStream(event.streams[0] ?? null);
                    },
                    () => {},
                );

            peer.onconnectionstatechange = () => {

                const current = callRef.current;

                if (!current.callId) return;

                if (
                    peer.connectionState === "connected"
                ) {

                    setCall(previous => ({
                        ...previous,
                        status: "in-call",
                    }));

                }

                else if (
                    ["failed", "disconnected", "closed"]
                        .includes(peer.connectionState)
                ) {

                    if (
                        peer.connectionState === "failed" ||
                        peer.connectionState === "closed"
                    ) {

                        endCall();

                    }

                }

            };

            const offer =
                await peer.createOffer();

            await peer.setLocalDescription(offer);

            websocketService.sendCallEvent(
                "call_offer",
                conversationId,
                callId,
                {
                    call_type: callType,
                    sdp: offer,
                }
            );

        }

        catch (error) {

            console.error(error);

            cleanup();

        }

    }

    //=====================================================
    // Accept an incoming call (async: caller may hang up)
    //=====================================================

    async function answerCall() {

        const incoming =
            incomingRef.current;

        if (!incoming) return;

        try {

            const stream =
                await navigator.mediaDevices.getUserMedia({
                    audio: true,
                    video: incoming.callType === "video",
                });

            setLocalStream(stream);

            setVideoEnabled(incoming.callType === "video");

            setIncomingCall(null);

            callRef.current = {
                conversationId: incoming.conversationId,
                callId: incoming.callId,
                callType: incoming.callType,
                peerId: incoming.from,
                peerName: incoming.peerName,
                status: "connecting",
            };

            setCall(callRef.current);

            const peer = await setupPeer(
                stream,
                (event) => {
                    setRemoteStream(event.streams[0] ?? null);
                },
                () => {},
            );

            peer.onconnectionstatechange = () => {

                const current = callRef.current;

                if (!current.callId) return;

                if (
                    peer.connectionState === "connected"
                ) {

                    setCall(previous => ({
                        ...previous,
                        status: "in-call",
                    }));

                }

                else if (
                    peer.connectionState === "failed" ||
                    peer.connectionState === "closed"
                ) {

                    endCall();

                }

            };

            await peer.setRemoteDescription(
                new RTCSessionDescription(
                    incoming.offer
                )
            );

            const answer =
                await peer.createAnswer();

            await peer.setLocalDescription(answer);

            websocketService.sendCallEvent(
                "call_answer",
                incoming.conversationId,
                incoming.callId,
                {
                    to: incoming.from,
                    sdp: answer,
                }
            );

        }

        catch (error) {

            console.error(error);

            cleanup();

        }

    }

    //=====================================================
    // Decline an incoming call
    //=====================================================

    function declineCall() {

        const incoming =
            incomingRef.current;

        if (!incoming) return;

        websocketService.sendCallEvent(
            "call_end",
            incoming.conversationId,
            incoming.callId,
            {
                to: incoming.from,
            }
        );

        cleanup();

    }

    //=====================================================
    // End the active call (also used on remote hang-up)
    //=====================================================

    function endCall() {

        const current = callRef.current;

        if (current.callId) {

            websocketService.sendCallEvent(
                "call_end",
                current.conversationId,
                current.callId,
                {
                    to: current.peerId,
                }
            );

        }

        cleanup();

    }

    //=====================================================
    // Media toggles
    //=====================================================

    function toggleMute() {

        setMuted(previous => {

            const next = !previous;

            localStream?.getAudioTracks().forEach(
                track => {
                    track.enabled = !next;
                }
            );

            return next;

        });

    }

    function toggleVideo() {

        setVideoEnabled(previous => {

            const next = !previous;

            localStream?.getVideoTracks().forEach(
                track => {
                    track.enabled = next;
                }
            );

            return next;

        });

    }

    //=====================================================
    // Signaling events
    //=====================================================

    useEffect(() => {

        const unsubscribe =
            subscribe((event) => {

                const selfId =
                    userRef.current?.id;

                if (
                    !event.conversation_id ||
                    !event.call_id ||
                    event.from === selfId
                ) {
                    return;
                }

                const current =
                    callRef.current;

                switch (event.event) {

                    case "call_offer": {

                        // Busy: politely reject another offer.
                        if (current.callId) {

                            websocketService.sendCallEvent(
                                "call_end",
                                event.conversation_id,
                                event.call_id,
                                {
                                    to: event.from,
                                }
                            );

                            return;

                        }

                        incomingRef.current = {
                            conversationId:
                                event.conversation_id,
                            callId: event.call_id,
                            callType:
                                event.call_type ?? "voice",
                            from: event.from,
                            offer: event.sdp,
                            peerName:
                                peerNameFor(
                                    event.conversation_id,
                                    event.from,
                                ),
                        };

                        setIncomingCall(
                            incomingRef.current
                        );

                        break;

                    }

                    case "call_answer":

                        if (
                            current.callId ===
                            event.call_id
                        ) {

                            try {

                                const peer =
                                    peerConnectionRef.current;

                                peer?.setRemoteDescription(
                                    new RTCSessionDescription(
                                        event.sdp
                                    )
                                );

                            }

                            catch (e) {

                                console.error(e);

                            }

                        }

                        break;

                    case "call_ice":

                        if (
                            current.callId ===
                            event.call_id &&
                            event.candidate
                        ) {

                            try {

                                peerConnectionRef.current
                                    ?.addIceCandidate(
                                        event.candidate
                                    );

                            }

                            catch (e) {

                                console.error(e);

                            }

                        }

                        break;

                    case "call_end":

                        if (
                            current.callId ===
                            event.call_id
                        ) {

                            cleanup();

                        }

                        else if (
                            incomingRef.current?.callId ===
                            event.call_id
                        ) {

                            setIncomingCall(null);

                        }

                        break;

                }

            });

        return unsubscribe;

    }, [subscribe, conversations]);

    //=====================================================
    // Auto-end when the page goes away / unmounts
    //=====================================================

    useEffect(() => {

        function handlePageHide() {

            const current = callRef.current;

            if (current.callId) {

                websocketService.sendCallEvent(
                    "call_end",
                    current.conversationId,
                    current.callId,
                    {
                        to: current.peerId,
                    }
                );

            }

        }

        window.addEventListener(
            "pagehide",
            handlePageHide
        );

        return () => {

            window.removeEventListener(
                "pagehide",
                handlePageHide
            );

            cleanup();

        };

    }, []);

    const value = {

        call,

        incomingCall,

        localStream,

        remoteStream,

        muted,

        videoEnabled,

        startCall,

        answerCall,

        declineCall,

        endCall,

        toggleMute,

        toggleVideo,

    };

    return (

        <CallContext.Provider value={value}>

            {children}

            {incomingCall && (

                <IncomingCallModal
                    call={incomingCall}
                    onAnswer={answerCall}
                    onDecline={declineCall}
                />

            )}

            {call.callId && call.status !== "ended" && (

                <ActiveCallOverlay />

            )}

        </CallContext.Provider>

    );

}

export function useCall() {

    return useContext(CallContext);

}
