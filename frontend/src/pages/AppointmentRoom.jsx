import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Camera,
  CameraOff,
  Check,
  CheckCheck,
  Clock3,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  RefreshCw,
  SendHorizontal,
  SwitchCamera,
  Video,
  XCircle,
} from "lucide-react";
import { api, getStoredUser } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { MODE_LABEL, fmtFull, fmtTime } from "../lib/format";
import { doctorLabel, patientLabel, usePeople } from "../lib/people";
import { useCall } from "../lib/useCall";
import { useChat } from "../lib/useChat";
import { useRoomSocket } from "../lib/useRoomSocket";
import { Alert, Badge, Button, Card, EmptyState, Loading, PageHeader, StatusBadge } from "../ui/kit";
import { SignalBars } from "../ui/doodles";
import { useToast } from "../ui/toast";
import ClinicalPanel from "./ClinicalPanel";

const CALL_COPY = {
  idle: { title: "Ready when you are", body: "Audio first — it works on two bars of signal." },
  connecting: { title: "Connecting…", body: "Finding the best path between your two phones." },
  waiting: { title: "Waiting for the other side", body: "You're in the room. They'll hear you the moment they join." },
  reconnecting: { title: "Signal dipped — reconnecting", body: "Hold on, the call resumes by itself. No need to hang up." },
  live: { title: "You're connected", body: "Speak slowly; the line may lag a little." },
  ended: { title: "Call ended", body: "Notes and chat are saved. You can rejoin anytime." },
};

function useCallTimer(running) {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  return `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
}

function CallStage({ call, videoFirst }) {
  const remoteVideoRef = useRef(null);
  const remoteAudioRef = useRef(null);
  const localVideoRef = useRef(null);
  const timer = useCallTimer(call.inCall);

  // Re-bind the remote stream whenever its tracks change (Safari needs a new object).
  useEffect(() => {
    const stream = new MediaStream(call.remoteStream.getTracks());
    if (remoteAudioRef.current) remoteAudioRef.current.srcObject = stream;
    if (remoteVideoRef.current) remoteVideoRef.current.srcObject = stream;
  }, [call.remoteVersion, call.remoteStream]);

  const localStream = call.cameraOn ? call.localStream() : null;
  useEffect(() => {
    const el = localVideoRef.current;
    if (el && el.srcObject !== localStream) el.srcObject = localStream;
  }, [localStream]);

  const copy = CALL_COPY[call.state];
  const stateClass = call.state === "live" ? "is-live" : ["connecting", "reconnecting", "waiting"].includes(call.state) ? "is-connecting" : "";

  return (
    <div className={`call ${stateClass}`}>
      <div className="call-status">
        <span className="rec-dot" /> {call.state}
      </div>
      <div className="call-timer">
        {call.state === "live" && call.quality && (
          <span data-tip={`${call.quality.rttMs ?? "?"} ms · ${call.quality.lossPct}% loss`} style={{ position: "relative", marginRight: "0.6rem" }}>
            <SignalBars level={call.quality.level + 1} />
          </span>
        )}
        {call.inCall && timer}
      </div>

      {/* Remote video stays mounted so its stream binding survives toggles. */}
      <video ref={remoteVideoRef} autoPlay playsInline muted style={{ display: call.remoteVideo ? "block" : "none" }} />
      {!call.remoteVideo && (
        <div className="call-center">
          <div className="call-orb">
            <Phone size={36} />
          </div>
          <h3>{copy.title}</h3>
          <p>{copy.body}</p>
        </div>
      )}
      <video ref={localVideoRef} autoPlay playsInline muted className="local-video" style={{ display: call.cameraOn ? "block" : "none" }} />
      <audio ref={remoteAudioRef} autoPlay />

      <div className="call-bar">
        {!call.inCall ? (
          <>
            <Button icon={Phone} onClick={() => call.join({ video: false })}>
              {call.state === "ended" ? "Rejoin" : "Join call"}
            </Button>
            <Button variant="secondary" icon={Video} onClick={() => call.join({ video: true })}>
              {videoFirst ? "Join with video" : "Video"}
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" icon={call.muted ? MicOff : Mic} onClick={call.toggleMute} aria-label={call.muted ? "Unmute" : "Mute"}>
              {call.muted ? "Unmute" : "Mute"}
            </Button>
            <Button
              variant="secondary"
              icon={call.cameraOn ? CameraOff : Camera}
              onClick={() => call.setCamera(!call.cameraOn)}
              aria-label={call.cameraOn ? "Camera off" : "Camera on"}
            >
              {call.cameraOn ? "Cam off" : "Cam on"}
            </Button>
            {call.cameraOn && <Button variant="secondary" icon={SwitchCamera} onClick={call.flipCamera} aria-label="Flip camera" />}
            <Button variant="danger" icon={PhoneOff} onClick={call.hangUp}>
              End
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function MessageStatus({ m, onRetry }) {
  if (m.status === "sending") return <Clock3 size={12} aria-label="Sending" />;
  if (m.status === "failed")
    return (
      <button className="link-btn" style={{ color: "inherit", fontSize: "0.7rem" }} onClick={() => onRetry(m.idempotency_key)}>
        <RefreshCw size={11} /> retry
      </button>
    );
  return <CheckCheck size={13} aria-label="Delivered" />;
}

export default function AppointmentRoom() {
  const { id: appointmentId } = useParams();
  const user = getStoredUser();
  const people = usePeople();
  const toast = useToast();

  const [appointment, setAppointment] = useState(null);
  const [iceServers, setIceServers] = useState([{ urls: "stun:stun.l.google.com:19302" }]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const chatEndRef = useRef(null);

  const active = appointment && ["pending", "confirmed"].includes(appointment.status);
  const { socket, status: link, onConnect } = useRoomSocket(Boolean(active));
  const chat = useChat({ socket, onConnect, appointmentId, myId: user?.id, enabled: Boolean(active) });
  const call = useCall({ socket, onConnect, appointmentId, myId: user?.id, iceServers });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data: appt } = await api.get(`/appointments/${appointmentId}`);
        if (!alive) return;
        setAppointment(appt);
        if (["pending", "confirmed"].includes(appt.status)) {
          const { data: room } = await api.post("/teleconsult/room", { appointment_id: appointmentId });
          if (alive && room.ice_servers?.length) setIceServers(room.ice_servers);
        }
      } catch (err) {
        if (alive) setLoadError(errorText(err, "Could not open this consultation room."));
      }
    })();
    return () => {
      alive = false;
    };
  }, [appointmentId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [chat.messages, chat.peerTyping]);

  function sendMessage(e) {
    e.preventDefault();
    if (!draft.trim()) return;
    chat.send(draft.trim());
    setDraft("");
  }

  async function setStatus(status) {
    try {
      const { data } = await api.patch(`/appointments/${appointmentId}`, { status });
      if (call.inCall) call.hangUp();
      setAppointment(data);
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

  const isPatient = user?.role === "patient";

  return (
    <Layout>
      <PageHeader
        garland={false}
        eyebrow={`${MODE_LABEL[appointment.consultation_mode]} · ${fmtFull(appointment.scheduled_at)}`}
        title={isPatient ? `With ${doctorLabel(people, appointment.doctor_id)}` : patientLabel(people, appointment.patient_id)}
      >
        <StatusBadge status={appointment.status} />
        {active && !isPatient && (
          <Button variant="secondary" size="sm" icon={Check} onClick={() => setStatus("completed")}>
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
      <Alert tone="orange" onClose={call.clearError}>{call.error}</Alert>

      <div className="grid-main">
        <div className="stack">
          {active && appointment.consultation_mode !== "store_forward" && (
            <CallStage call={call} videoFirst={appointment.consultation_mode === "live_video"} />
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
            {active ? (
              <Badge tone={link === "online" ? "green" : "orange"} dot>
                {link === "online" ? "live" : "reconnecting…"}
              </Badge>
            ) : (
              <span className="muted" style={{ fontSize: "0.8rem" }}>
                Read-only
              </span>
            )}
          </div>
          <div className="chat-log">
            {chat.messages.length === 0 && <EmptyState doodle="lantern" {...EMPTY.chat} />}
            {chat.messages.map((m) => {
              const mine = m.sender_id === user?.id;
              return (
                <div key={m.idempotency_key || m.id} className={`bubble ${mine ? "mine" : ""} ${m.status === "failed" ? "is-failed" : ""}`}>
                  {m.body}
                  <time>
                    {fmtTime(m.created_at)} {mine && <MessageStatus m={m} onRetry={chat.retry} />}
                  </time>
                </div>
              );
            })}
            {chat.peerTyping && (
              <div className="bubble typing" aria-label="typing">
                <i />
                <i />
                <i />
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          {active && (
            <form onSubmit={sendMessage} className="chat-form">
              <input
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  chat.typing();
                }}
                placeholder={link === "online" ? "Type a message…" : "Offline — messages will send when back"}
                aria-label="Message"
              />
              <Button icon={SendHorizontal} aria-label="Send" disabled={!draft.trim()} />
            </form>
          )}
        </Card>
      </div>
    </Layout>
  );
}
