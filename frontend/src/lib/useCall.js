import { useCallback, useEffect, useRef, useState } from "react";

// Low-bandwidth defaults: voice-grade audio, small video, capped bitrate.
const AUDIO = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
const VIDEO = (facingMode) => ({ width: { ideal: 320 }, height: { ideal: 240 }, frameRate: { max: 15 }, facingMode });
const VIDEO_MAX_BITRATE = 250_000;

/**
 * Peer-to-peer WebRTC call over our Socket.IO signalling, hardened for
 * rural networks:
 *
 * - "Perfect negotiation" (MDN pattern): either side may (re)negotiate at any
 *   time — turning video on, a reconnect, both joining at once — and offer
 *   collisions resolve themselves. The polite peer is picked by user id.
 * - ICE restarts on "failed", and after a few seconds of "disconnected".
 * - If either side's socket drops, re-joining the room triggers a fresh
 *   peer connection; local mic/camera are kept, so the call resumes.
 *
 * states: idle → waiting (alone in the room) → connecting → live
 *         ↘ reconnecting ↗                    → ended
 */
export function useCall({ socket, onConnect, appointmentId, myId, iceServers }) {
  const [state, setState] = useState("idle");
  const [muted, setMuted] = useState(false);
  const [cameraOn, setCameraOn] = useState(false);
  const [remoteVideo, setRemoteVideo] = useState(false);
  const [quality, setQuality] = useState(null); // { rttMs, lossPct, level: 0-3 }
  const [error, setError] = useState("");
  const [remoteVersion, setRemoteVersion] = useState(0); // bumps when remote tracks change

  const pcRef = useRef(null);
  const localRef = useRef(null); // MediaStream
  const remoteRef = useRef(new MediaStream());
  const facingRef = useRef("user");
  const inCall = useRef(false);
  const makingOffer = useRef(false);
  const ignoreOffer = useRef(false);
  const politeRef = useRef(true);
  const disconnectTimer = useRef(null);
  const peerGoneTimer = useRef(null);
  const iceRef = useRef(iceServers);
  iceRef.current = iceServers;

  const send = useCallback(
    (data) => socket?.emit("call:signal", { appointment_id: appointmentId, data }),
    [socket, appointmentId]
  );

  const closePc = useCallback(() => {
    clearTimeout(disconnectTimer.current);
    if (pcRef.current) {
      pcRef.current.onnegotiationneeded = null;
      pcRef.current.onicecandidate = null;
      pcRef.current.ontrack = null;
      pcRef.current.oniceconnectionstatechange = null;
      pcRef.current.close();
    }
    pcRef.current = null;
    remoteRef.current.getTracks().forEach((t) => remoteRef.current.removeTrack(t));
    setRemoteVersion((v) => v + 1);
    setRemoteVideo(false);
    setQuality(null);
  }, []);

  const capVideoBitrate = (sender) => {
    try {
      const params = sender.getParameters();
      params.encodings = params.encodings?.length ? params.encodings : [{}];
      params.encodings[0].maxBitrate = VIDEO_MAX_BITRATE;
      sender.setParameters(params).catch(() => {});
    } catch {
      /* older browsers — fine without a cap */
    }
  };

  /** Fresh RTCPeerConnection with our tracks; negotiation starts by itself. */
  const newPc = useCallback(() => {
    closePc();
    const pc = new RTCPeerConnection({ iceServers: iceRef.current });
    pcRef.current = pc;
    if (import.meta.env.DEV) window.__gcPc = pc; // lets the e2e tests read stats

    pc.onnegotiationneeded = async () => {
      try {
        makingOffer.current = true;
        await pc.setLocalDescription();
        send({ description: pc.localDescription });
      } catch (e) {
        console.warn("negotiation failed", e);
      } finally {
        makingOffer.current = false;
      }
    };
    pc.onicecandidate = ({ candidate }) => candidate && send({ candidate });
    pc.ontrack = ({ track }) => {
      remoteRef.current.getTracks().filter((t) => t.kind === track.kind).forEach((t) => remoteRef.current.removeTrack(t));
      remoteRef.current.addTrack(track);
      setRemoteVersion((v) => v + 1);
      // Remote `muted` flags are unreliable across renegotiations, so video
      // shows when a track arrives and follows the peer's camera signals.
      if (track.kind === "video") {
        setRemoteVideo(true);
        track.onended = () => setRemoteVideo(false);
      }
    };
    pc.oniceconnectionstatechange = () => {
      const s = pc.iceConnectionState;
      clearTimeout(disconnectTimer.current);
      if (s === "connected" || s === "completed") {
        clearTimeout(peerGoneTimer.current);
        setState("live");
      }
      else if (s === "checking") setState((cur) => (cur === "live" ? "reconnecting" : "connecting"));
      else if (s === "failed") {
        setState("reconnecting");
        pc.restartIce();
      } else if (s === "disconnected") {
        setState("reconnecting");
        disconnectTimer.current = setTimeout(() => pc.iceConnectionState === "disconnected" && pc.restartIce(), 4000);
      }
    };

    localRef.current?.getTracks().forEach((track) => {
      const sender = pc.addTrack(track, localRef.current);
      if (track.kind === "video") {
        sender._gcVideo = true;
        capVideoBitrate(sender);
      }
    });
    return pc;
  }, [closePc, send]);

  // Signalling + presence events.
  useEffect(() => {
    if (!socket) return;

    const onSignal = async ({ appointment_id, data, from }) => {
      if (appointment_id !== appointmentId || !inCall.current) return;
      politeRef.current = String(myId) > String(from);
      let pc = pcRef.current;
      if (!pc) pc = newPc();
      try {
        if (data.description) {
          const desc = data.description;
          const collision = desc.type === "offer" && (makingOffer.current || pc.signalingState !== "stable");
          ignoreOffer.current = !politeRef.current && collision;
          if (ignoreOffer.current) return;
          await pc.setRemoteDescription(desc);
          if (desc.type === "offer") {
            await pc.setLocalDescription();
            send({ description: pc.localDescription });
          }
        } else if (data.candidate) {
          try {
            await pc.addIceCandidate(data.candidate);
          } catch (e) {
            if (!ignoreOffer.current) console.warn("ICE candidate rejected", e);
          }
        } else if (typeof data.camera === "boolean") {
          setRemoteVideo(data.camera);
        }
      } catch (e) {
        console.warn("signal handling failed", e);
      }
    };
    const onPeerJoined = ({ appointment_id }) => {
      if (appointment_id !== appointmentId || !inCall.current) return;
      clearTimeout(peerGoneTimer.current);
      setState("connecting");
      newPc(); // the newcomer has no state — start a clean negotiation
    };
    const onPeerLeft = ({ appointment_id }) => {
      if (appointment_id !== appointmentId || !inCall.current) return;
      closePc();
      setState("waiting");
    };
    const onPeerOffline = ({ appointment_id }) => {
      if (appointment_id !== appointmentId || !inCall.current) return;
      setState("reconnecting");
      // If they don't come back, stop pretending: show "waiting" instead.
      clearTimeout(peerGoneTimer.current);
      peerGoneTimer.current = setTimeout(() => {
        const s = pcRef.current?.iceConnectionState;
        if (inCall.current && s !== "connected" && s !== "completed") {
          closePc();
          setState("waiting");
        }
      }, 20000);
    };

    socket.on("call:signal", onSignal);
    socket.on("call:peer-joined", onPeerJoined);
    socket.on("call:peer-left", onPeerLeft);
    socket.on("call:peer-offline", onPeerOffline);
    return () => {
      socket.off("call:signal", onSignal);
      socket.off("call:peer-joined", onPeerJoined);
      socket.off("call:peer-left", onPeerLeft);
      socket.off("call:peer-offline", onPeerOffline);
    };
  }, [socket, appointmentId, myId, newPc, closePc, send]);

  const joinRoom = useCallback(
    (s) => {
      s.timeout(10000).emit("call:join", { appointment_id: appointmentId }, (err, ack) => {
        if (err || !ack?.ok) return setState("reconnecting");
        if (ack.peers > 0) {
          setState("connecting");
          newPc();
        } else {
          setState("waiting");
        }
      });
    },
    [appointmentId, newPc]
  );

  // Our own socket reconnected mid-call: re-enter the room and renegotiate.
  useEffect(() => {
    if (!socket) return;
    return onConnect((s) => inCall.current && joinRoom(s));
  }, [socket, onConnect, joinRoom]);

  // Call quality from WebRTC stats, every 3 s while live.
  useEffect(() => {
    if (state !== "live") return;
    const t = setInterval(async () => {
      const pc = pcRef.current;
      if (!pc) return;
      const stats = await pc.getStats();
      let rtt = null;
      let lost = 0;
      let received = 0;
      stats.forEach((r) => {
        if (r.type === "candidate-pair" && r.nominated && r.currentRoundTripTime != null) rtt = r.currentRoundTripTime * 1000;
        if (r.type === "inbound-rtp" && r.kind === "audio") {
          lost += r.packetsLost || 0;
          received += r.packetsReceived || 0;
        }
      });
      const lossPct = received + lost ? (lost / (received + lost)) * 100 : 0;
      const level = rtt == null ? 2 : rtt < 250 && lossPct < 2 ? 3 : rtt < 600 && lossPct < 8 ? 2 : 1;
      setQuality({ rttMs: rtt == null ? null : Math.round(rtt), lossPct: Math.round(lossPct * 10) / 10, level });
    }, 3000);
    return () => clearInterval(t);
  }, [state]);

  const join = useCallback(
    async ({ video = false } = {}) => {
      setError("");
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("This browser can't use the microphone here. Open the app over https (or localhost).");
        return;
      }
      try {
        localRef.current = await navigator.mediaDevices.getUserMedia({
          audio: AUDIO,
          video: video ? VIDEO(facingRef.current) : false,
        });
      } catch {
        if (!video) {
          setError("Microphone permission is needed for the call. Allow it in the browser's address bar.");
          return;
        }
        // Camera refused or missing — fall back to audio only.
        try {
          localRef.current = await navigator.mediaDevices.getUserMedia({ audio: AUDIO });
          setError("Camera unavailable — joined with audio only.");
        } catch {
          setError("Microphone permission is needed for the call.");
          return;
        }
      }
      setCameraOn(localRef.current.getVideoTracks().length > 0);
      setMuted(false);
      inCall.current = true;
      setState("connecting");
      if (socket?.connected) joinRoom(socket);
      else setState("reconnecting"); // joins automatically once the socket is back
    },
    [socket, joinRoom]
  );

  const hangUp = useCallback(() => {
    inCall.current = false;
    socket?.emit("call:leave", { appointment_id: appointmentId });
    closePc();
    localRef.current?.getTracks().forEach((t) => t.stop());
    localRef.current = null;
    setCameraOn(false);
    setState("ended");
  }, [socket, appointmentId, closePc]);

  // Closing or reloading the tab doesn't run React cleanup — say goodbye
  // explicitly so the other side shows "waiting" right away.
  useEffect(() => {
    const bye = () => inCall.current && socket?.emit("call:leave", { appointment_id: appointmentId });
    window.addEventListener("pagehide", bye);
    return () => window.removeEventListener("pagehide", bye);
  }, [socket, appointmentId]);

  // Leave cleanly when the page unmounts (always with the latest hangUp).
  const hangUpRef = useRef(hangUp);
  hangUpRef.current = hangUp;
  useEffect(() => () => inCall.current && hangUpRef.current(), []);

  const toggleMute = useCallback(() => {
    const next = !muted;
    localRef.current?.getAudioTracks().forEach((t) => (t.enabled = !next));
    setMuted(next);
  }, [muted]);

  const setCamera = useCallback(
    async (on) => {
      const local = localRef.current;
      if (!local) return;
      const pc = pcRef.current;
      const sender = pc?.getSenders().find((s) => s.track?.kind === "video" || (s.track === null && s._gcVideo));
      if (!on) {
        local.getVideoTracks().forEach((t) => {
          t.stop();
          local.removeTrack(t);
        });
        if (sender) await sender.replaceTrack(null);
        send({ camera: false });
        setCameraOn(false);
        return;
      }
      try {
        const cam = await navigator.mediaDevices.getUserMedia({ video: VIDEO(facingRef.current) });
        const [track] = cam.getVideoTracks();
        local.addTrack(track);
        if (sender) {
          await sender.replaceTrack(track); // no renegotiation needed
        } else if (pc) {
          const s = pc.addTrack(track, local); // triggers negotiationneeded
          s._gcVideo = true;
          capVideoBitrate(s);
        }
        send({ camera: true });
        setCameraOn(true);
      } catch {
        setError("Camera access wasn't granted.");
      }
    },
    [send]
  );

  /** Front ↔ back camera, for showing a wound or a rash on a phone. */
  const flipCamera = useCallback(async () => {
    facingRef.current = facingRef.current === "user" ? "environment" : "user";
    if (cameraOn) {
      await setCamera(false);
      await setCamera(true);
    }
  }, [cameraOn, setCamera]);

  return {
    state,
    inCall: state !== "idle" && state !== "ended",
    muted,
    cameraOn,
    remoteVideo,
    quality,
    error,
    clearError: () => setError(""),
    localStream: () => localRef.current,
    remoteStream: remoteRef.current,
    remoteVersion,
    join,
    hangUp,
    toggleMute,
    setCamera,
    flipCamera,
  };
}
