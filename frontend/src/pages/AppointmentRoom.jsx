import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { io } from "socket.io-client";
import { CheckCheck, Mic, MicOff, Phone, PhoneOff, SendHorizontal, Video, XCircle } from "lucide-react";
import { api, getStoredUser, SOCKET_URL } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { MODE_LABEL, fmtFull, fmtTime } from "../lib/format";
import { doctorLabel, patientLabel, usePeople } from "../lib/people";
import { Alert, Button, Card, EmptyState, Loading, PageHeader, StatusBadge } from "../ui/kit";
import { useToast } from "../ui/toast";
import ClinicalPanel from "./ClinicalPanel";

const CALL_COPY = {
  idle: { title: "Ready when you are", body: "Audio first — it works on two bars of signal." },
  connecting: { title: "Ringing the other side…", body: "Waiting for them to join the room. Keep this tab open." },
  "in-call": { title: "You're connected", body: "Speak slowly; the line may lag a little." },
  ended: { title: "Call ended", body: "Notes and chat are saved. You can rejoin anytime." },
};

function useCallTimer(running) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    if (!running) return;
    setSecs(0);
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  return `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
}

export default function AppointmentRoom() {
  const { id: appointmentId } = useParams();
  const user = getStoredUser();
  const people = usePeople();
  const toast = useToast();

  const [appointment, setAppointment] = useState(null);
  const [callState, setCallState] = useState("idle");
  const [micOn, setMicOn] = useState(false);
  const [muted, setMuted] = useState(false);
  const [videoOn, setVideoOn] = useState(false);
  const [remoteVideoOn, setRemoteVideoOn] = useState(false);
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const socketRef = useRef(null);
  const pcRef = useRef(null);
  const localStreamRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const remoteVideoRef = useRef(null);
  const localVideoRef = useRef(null);
  const iceServersRef = useRef([{ urls: "stun:stun.l.google.com:19302" }]);
  const chatEndRef = useRef(null);

  const timer = useCallTimer(callState === "in-call");

  // ── Setup: appointment, chat history, socket connection ─────────────────
  useEffect(() => {
    let cancelled = false;

    async function setup() {
      try {
        const { data: appt } = await api.get(`/appointments/${appointmentId}`);
        if (cancelled) return;
        setAppointment(appt);
        const { data: history } = await api.get(`/messages/${appointmentId}`);
        if (cancelled) return;
        setMessages(history);

        if (!["pending", "confirmed"].includes(appt.status)) return; // room closed; read-only
        const { data: room } = await api.post("/teleconsult/room", { appointment_id: appointmentId });
        if (cancelled) return;
        if (room.ice_servers?.length) iceServersRef.current = room.ice_servers;

        const socket = io(SOCKET_URL, { auth: { token: localStorage.getItem("access_token") }, transports: ["websocket"] });
        socketRef.current = socket;

        socket.on("connect_error", (err) => setError(`Realtime connection failed: ${err.message}`));
        socket.on("call:peer-joined", async () => {
          // We were already in the room, so we send the offer to the newcomer.
          if (!localStreamRef.current) return;
          await ensurePeerConnection();
          await sendOffer();
        });
        socket.on("call:signal", async ({ data }) => {
          const pc = await ensurePeerConnection();
          if (data.type === "offer") {
            await pc.setRemoteDescription({ type: "offer", sdp: data.sdp });
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            socket.emit("call:signal", { appointment_id: appointmentId, data: { type: "answer", sdp: answer.sdp } });
          } else if (data.type === "answer") {
            await pc.setRemoteDescription({ type: "answer", sdp: data.sdp });
          } else if (data.type === "ice-candidate" && data.candidate) {
            try {
              await pc.addIceCandidate(data.candidate);
            } catch {
              /* candidate arrived before the remote description; safe to ignore */
            }
          }
        });
        socket.on("call:peer-left", () => {
          setCallState("ended");
          teardownCall();
        });
        socket.on("chat:message", (msg) => setMessages((prev) => (prev.some((m) => m.id === msg.id) ? prev : [...prev, msg])));
        socket.on("call:error", (e) => setError(e.message));
        socket.on("chat:error", (e) => setError(e.message));

        socket.emit("chat:join", { appointment_id: appointmentId });
      } catch (err) {
        if (!cancelled) setLoadError(errorText(err, "Could not open this consultation room."));
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
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  async function sendOffer() {
    const pc = pcRef.current;
    if (!pc) return;
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    socketRef.current?.emit("call:signal", { appointment_id: appointmentId, data: { type: "offer", sdp: offer.sdp } });
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
      if (["disconnected", "failed", "closed"].includes(pc.connectionState)) setCallState("ended");
    };
    if (!localStreamRef.current) {
      // Audio-first, per the paper's low-bandwidth design.
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
      // Joining the call room tells anyone already there to send us an offer.
      socketRef.current?.emit("call:join", { appointment_id: appointmentId });
    } catch {
      setError("Microphone access is needed for the call. Check the browser's permission prompt.");
      setCallState("idle");
    }
  }

  function toggleMute() {
    const next = !muted;
    localStreamRef.current?.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMuted(next);
  }

  async function enableVideo() {
    setError("");
    try {
      const pc = await ensurePeerConnection();
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, frameRate: 15 } });
      const [track] = stream.getVideoTracks();
      localStreamRef.current.addTrack(track);
      pc.addTrack(track, localStreamRef.current);
      setVideoOn(true);
      setTimeout(() => localVideoRef.current && (localVideoRef.current.srcObject = localStreamRef.current), 0);
      if (pc.signalingState === "stable") await sendOffer();
    } catch {
      setError("Camera access wasn't granted.");
    }
  }

  function teardownCall() {
    pcRef.current?.close();
    pcRef.current = null;
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    localStreamRef.current = null;
    setMicOn(false);
    setMuted(false);
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

  async function setStatus(status) {
    try {
      const { data } = await api.patch(`/appointments/${appointmentId}`, { status });
      setAppointment(data);
      if (status !== "confirmed") endCall();
      toast(status === "completed" ? "Marked as done. Shabash!" : "Appointment cancelled.", status === "completed" ? "green" : "orange");
    } catch (err) {
      setError(errorText(err, "Could not update the appointment."));
    }
  }

  if (loadError) {
    return (
      <Layout>
        <EmptyState doodle="lantern" title="Can't open this room" body={loadError} />
      </Layout>
    );
  }
  if (!appointment) {
    return (
      <Layout>
        <Loading lines={4} />
      </Layout>
    );
  }

  const active = ["pending", "confirmed"].includes(appointment.status);
  const isPatient = user?.role === "patient";
  const copy = CALL_COPY[callState];
  const stateClass = callState === "in-call" ? "is-live" : callState === "connecting" ? "is-connecting" : "";

  return (
    <Layout>
      <PageHeader
        garland={false}
        eyebrow={`${MODE_LABEL[appointment.consultation_mode]} · ${fmtFull(appointment.scheduled_at)}`}
        title={isPatient ? `With ${doctorLabel(people, appointment.doctor_id)}` : patientLabel(people, appointment.patient_id)}
      >
        <StatusBadge status={appointment.status} />
        {active && !isPatient && (
          <Button variant="secondary" size="sm" icon={CheckCheck} onClick={() => setStatus("completed")}>
            Mark done
          </Button>
        )}
        {active && (
          <Button variant="ghost" size="sm" icon={XCircle} onClick={() => setStatus("cancelled")}>
            Cancel
          </Button>
        )}
      </PageHeader>

      <Alert onClose={() => setError("")}>{error}</Alert>

      <div className="grid-main">
        <div className="stack">
          {active && appointment.consultation_mode !== "store_forward" && (
            <div className={`call ${stateClass}`}>
              <div className="call-status">
                <span className="rec-dot" /> {callState.replace("-", " ")}
              </div>
              {callState === "in-call" && <div className="call-timer">{timer}</div>}

              <video ref={remoteVideoRef} autoPlay playsInline style={{ display: remoteVideoOn ? "block" : "none" }} />
              {!remoteVideoOn && (
                <div className="call-center">
                  <div className="call-orb">
                    <Phone size={36} />
                  </div>
                  <h3>{copy.title}</h3>
                  <p>{copy.body}</p>
                </div>
              )}
              {videoOn && <video ref={localVideoRef} autoPlay playsInline muted className="local-video" />}
              <audio ref={remoteAudioRef} autoPlay />

              <div className="call-bar">
                {callState === "idle" || callState === "ended" ? (
                  <Button icon={Phone} onClick={startCall}>
                    {callState === "ended" ? "Rejoin" : "Join call"}
                  </Button>
                ) : (
                  <>
                    <Button variant="secondary" icon={muted ? MicOff : Mic} onClick={toggleMute} disabled={!micOn}>
                      {muted ? "Unmute" : "Mute"}
                    </Button>
                    {!videoOn && (
                      <Button variant="secondary" icon={Video} onClick={enableVideo}>
                        Video
                      </Button>
                    )}
                    <Button variant="danger" icon={PhoneOff} onClick={endCall}>
                      End
                    </Button>
                  </>
                )}
              </div>
            </div>
          )}
          {appointment.notes && (
            <Card className="tip">
              <SendHorizontal size={18} />
              <p>
                <b>Note from booking</b>
                {appointment.notes}
              </p>
            </Card>
          )}
          {!isPatient && <ClinicalPanel appointment={appointment} />}
        </div>

        <Card className="chat" style={{ position: "sticky", top: "1.5rem" }}>
          <div className="chat-head">
            <h3>Chat</h3>
            <span className="muted" style={{ fontSize: "0.8rem" }}>
              {active ? "Saved even if the call drops" : "Read-only"}
            </span>
          </div>
          <div className="chat-log">
            {messages.length === 0 && <EmptyState doodle="lantern" {...EMPTY.chat} />}
            {messages.map((m) => (
              <div key={m.id} className={`bubble ${m.sender_id === user?.id ? "mine" : ""}`}>
                {m.body}
                <time>{fmtTime(m.created_at)}</time>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
          {active && (
            <form onSubmit={sendMessage} className="chat-form">
              <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type a message…" aria-label="Message" />
              <Button icon={SendHorizontal} aria-label="Send" disabled={!draft.trim()} />
            </form>
          )}
        </Card>
      </div>
    </Layout>
  );
}
