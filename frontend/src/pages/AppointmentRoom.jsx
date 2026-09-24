import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { io } from "socket.io-client";
import { api, SOCKET_URL, getStoredUser } from "../api";
import ClinicalPanel from "./ClinicalPanel";
import Layout from "../components/Layout";

export default function AppointmentRoom() {
  const { id: appointmentId } = useParams();
  const user = getStoredUser();

  const [appointment, setAppointment] = useState(null);
  const [callState, setCallState] = useState("idle"); // idle | connecting | in-call | ended
  const [micOn, setMicOn] = useState(false);
  const [videoOn, setVideoOn] = useState(false);
  const [remoteVideoOn, setRemoteVideoOn] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  const socketRef = useRef(null);
  const pcRef = useRef(null);
  const localStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const localVideoRef = useRef(null);
  const iceServersRef = useRef([{ urls: "stun:stun.l.google.com:19302" }]);
  const chatEndRef = useRef(null);

  // ── Setup: room info, chat history, socket connection ──────────────────
  useEffect(() => {
    let cancelled = false;

    async function setup() {
      try {
        const [{ data: room }, { data: history }, { data: appt }] = await Promise.all([
          api.post("/teleconsult/room", { appointment_id: appointmentId }),
          api.get(`/messages/${appointmentId}`),
          api.get(`/appointments/${appointmentId}`),
        ]);
        if (cancelled) return;
        iceServersRef.current = room.ice_servers?.length
          ? room.ice_servers
          : iceServersRef.current;
        setMessages(history);
        setAppointment(appt);

        const token = localStorage.getItem("access_token");
        const socket = io(SOCKET_URL, {
          auth: { token },
          transports: ["websocket"],
        });
        socketRef.current = socket;

        socket.on("connect_error", (err) => setError(`Realtime connection failed: ${err.message}`));

        socket.on("call:peer-joined", async () => {
          // We were already in the room, so we initiate the offer to the newcomer.
          await ensurePeerConnection();
          await sendOffer();
        });

        socket.on("call:signal", async ({ data }) => {
          const pc = await ensurePeerConnection();
          if (data.type === "offer") {
            await pc.setRemoteDescription({ type: "offer", sdp: data.sdp });
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.emit("call:signal", {
              appointment_id: appointmentId,
              data: { type: "answer", sdp: answer.sdp },
            });
          } else if (data.type === "answer") {
            await pc.setRemoteDescription({ type: "answer", sdp: data.sdp });
          } else if (data.type === "ice-candidate" && data.candidate) {
            try {
              await pc.addIceCandidate(data.candidate);
            } catch {
              /* candidate arrived before remote description; safe to ignore */
            }
          }
        });

        socket.on("call:peer-left", () => {
          setCallState("ended");
          teardownCall();
        });

        socket.on("chat:message", (msg) => {
          setMessages((prev) => [...prev, msg]);
        });

        socket.on("call:error", (e) => setError(e.message));
        socket.on("chat:error", (e) => setError(e.message));

        socket.emit("call:join", { appointment_id: appointmentId });
        socket.emit("chat:join", { appointment_id: appointmentId });
      } catch (err) {
        if (!cancelled) setError(err.response?.data?.detail || "Could not load appointment room.");
      }
    }

    setup();
    return () => {
      cancelled = true;
      socketRef.current?.emit("call:leave", { appointment_id: appointmentId });
      socketRef.current?.disconnect();
      teardownCall();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appointmentId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function sendOffer() {
    const pc = pcRef.current;
    if (!pc) return;
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socketRef.current?.emit("call:signal", {
      appointment_id: appointmentId,
      data: { type: "offer", sdp: offer.sdp },
    });
  }

  async function ensurePeerConnection() {
    if (pcRef.current) return pcRef.current;
    const pc = new RTCPeerConnection({ iceServers: iceServersRef.current });

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        socketRef.current?.emit("call:signal", {
          appointment_id: appointmentId,
          data: { type: "ice-candidate", candidate: event.candidate },
        });
      }
    };
    pc.ontrack = (event) => {
      if (event.track.kind === "video") {
        if (remoteVideoRef.current) remoteVideoRef.current.srcObject = event.streams[0];
        setRemoteVideoOn(true);
      } else if (remoteAudioRef.current) {
        remoteAudioRef.current.srcObject = event.streams[0];
      }
      setCallState("in-call");
    };
    pc.onconnectionstatechange = () => {
      if (["disconnected", "failed", "closed"].includes(pc.connectionState)) {
        setCallState("ended");
      }
    };

    if (!localStreamRef.current) {
      // Audio-first, per the paper's low-bandwidth design — video is not
      // requested here at all, keeping data use minimal by default.
      localStreamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicOn(true);
    }
    localStreamRef.current.getTracks().forEach((track) => pc.addTrack(track, localStreamRef.current));

    pcRef.current = pc;
    return pc;
  }

  async function startCall() {
    setError("");
    setCallState("connecting");
    try {
      await ensurePeerConnection();
      // If we're first in the room, nothing to offer yet — we wait for
      // "call:peer-joined" to fire when the other side connects.
    } catch {
      setError("Microphone access is required to start the call.");
      setCallState("idle");
    }
  }

  async function toggleVideo() {
    if (videoOn) return; // keeping this one-directional keeps the UX simple
    setError("");
    try {
      const pc = await ensurePeerConnection();
      const videoStream = await navigator.mediaDevices.getUserMedia({ video: true });
      const [track] = videoStream.getVideoTracks();
      localStreamRef.current.addTrack(track);
      pc.addTrack(track, localStreamRef.current);
      if (localVideoRef.current) localVideoRef.current.srcObject = localStreamRef.current;
      setVideoOn(true);
      // Renegotiate — the other side's existing "offer" handler covers this
      // whether it's the first offer or a mid-call renegotiation.
      if (pc.signalingState === "stable") await sendOffer();
    } catch {
      setError("Camera access was not granted.");
    }
  }

  function teardownCall() {
    pcRef.current?.close();
    pcRef.current = null;
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    setMicOn(false);
    setVideoOn(false);
    setRemoteVideoOn(false);
  }

  function endCall() {
    socketRef.current?.emit("call:leave", { appointment_id: appointmentId });
    teardownCall();
    setCallState("ended");
  }

  function sendMessage(e) {
    e.preventDefault();
    if (!draft.trim()) return;
    socketRef.current?.emit("chat:message", {
      appointment_id: appointmentId,
      body: draft.trim(),
      idempotency_key: crypto.randomUUID(),
    });
    setDraft("");
  }

  return (
    <Layout>
      <div className="room">
        <header className="room-header">
          <h2>Consultation</h2>
          <span className={`status-pill status-${callState}`}>{callState}</span>
        </header>

        {error && <p className="error">{error}</p>}

        <section className="call-panel">
          <div className="video-stage">
            <video ref={remoteVideoRef} autoPlay playsInline className={remoteVideoOn ? "" : "hidden"} />
            {!remoteVideoOn && callState === "in-call" && (
              <div className="audio-only-hint">Audio call — no video from the other side</div>
            )}
            {videoOn && <video ref={localVideoRef} autoPlay playsInline muted className="local-video" />}
          </div>
          <audio ref={remoteAudioRef} autoPlay />

          <div className="call-controls">
            {callState === "idle" || callState === "ended" ? (
              <button className="button" onClick={startCall}>
                {callState === "ended" ? "Rejoin call" : "Join audio call"}
              </button>
            ) : (
              <>
                <button className="button danger" onClick={endCall}>
                  End call
                </button>
                {!videoOn && (
                  <button className="button secondary" onClick={toggleVideo}>
                    Enable video
                  </button>
                )}
              </>
            )}
          </div>
          <p className="meta">
            {micOn ? "Microphone live · audio-first WebRTC, P2P" : "Microphone not active"}
            {videoOn && " · video on"}
          </p>
        </section>

        {appointment && <ClinicalPanel appointment={appointment} />}

        <section className="chat-panel">
          <div className="chat-log">
            {messages.map((m) => (
              <div key={m.id} className={m.sender_id === user?.id ? "msg mine" : "msg"}>
                <span>{m.body}</span>
                <time>{new Date(m.created_at).toLocaleTimeString()}</time>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
          <form onSubmit={sendMessage} className="chat-form">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message…"
            />
            <button type="submit">Send</button>
          </form>
        </section>
      </div>
    </Layout>
  );
}
