import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

const outboxKey = (id) => `gc-outbox-${id}`;

function loadOutbox(id) {
  try {
    return JSON.parse(localStorage.getItem(outboxKey(id)) || "[]");
  } catch {
    return [];
  }
}

function saveOutbox(id, items) {
  try {
    if (items.length) localStorage.setItem(outboxKey(id), JSON.stringify(items));
    else localStorage.removeItem(outboxKey(id));
  } catch {
    /* storage full / private mode — messages still retry while the tab is open */
  }
}

function merge(list, incoming) {
  const seen = new Set(list.map((m) => m.id));
  const keys = new Map(list.map((m, i) => [m.idempotency_key, i]));
  const next = [...list];
  for (const m of incoming) {
    if (seen.has(m.id)) continue;
    const pendingIdx = m.idempotency_key ? keys.get(m.idempotency_key) : undefined;
    if (pendingIdx !== undefined) next[pendingIdx] = { ...m, status: "sent" };
    else next.push({ ...m, status: "sent" });
    seen.add(m.id);
  }
  return next.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
}

/**
 * Chat that never loses a message:
 * - sends are optimistic and kept in an outbox (also in localStorage) until
 *   the server acks them; the outbox is flushed on every reconnect
 * - the same idempotency key is reused on retry, so no duplicates
 * - after each reconnect, history is back-filled over REST
 */
export function useChat({ socket, onConnect, appointmentId, myId, enabled }) {
  const [messages, setMessages] = useState([]);
  const [peerTyping, setPeerTyping] = useState(false);
  const outbox = useRef(loadOutbox(appointmentId));
  const lastTypingSent = useRef(0);
  const typingTimer = useRef(null);

  const persistOutbox = () => saveOutbox(appointmentId, outbox.current);

  const deliver = useCallback(
    (s, item) => {
      s.timeout(10000).emit(
        "chat:message",
        { appointment_id: appointmentId, body: item.body, idempotency_key: item.idempotency_key },
        (err, ack) => {
          if (err) return; // stays in the outbox; retried on reconnect
          if (!ack?.ok) {
            setMessages((list) => list.map((m) => (m.idempotency_key === item.idempotency_key ? { ...m, status: "failed", error: ack?.error } : m)));
            outbox.current = outbox.current.filter((o) => o.idempotency_key !== item.idempotency_key);
            persistOutbox();
            return;
          }
          outbox.current = outbox.current.filter((o) => o.idempotency_key !== item.idempotency_key);
          persistOutbox();
          setMessages((list) => merge(list, [ack.message]));
        }
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [appointmentId]
  );

  // Initial history + any unsent messages from a previous visit.
  useEffect(() => {
    let alive = true;
    api
      .get(`/messages/${appointmentId}`)
      .then(({ data }) => {
        if (!alive) return;
        const pending = outbox.current.map((o) => ({ ...o, sender_id: myId, status: "sending" }));
        setMessages(merge(pending, data));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [appointmentId, myId]);

  // Join on every (re)connect, back-fill, then flush the outbox.
  useEffect(() => {
    if (!enabled || !socket) return;
    const off = onConnect((s) => {
      s.emit("chat:join", { appointment_id: appointmentId });
      api
        .get(`/messages/${appointmentId}`)
        .then(({ data }) => setMessages((list) => merge(list, data)))
        .catch(() => {});
      outbox.current.forEach((item) => deliver(s, item));
    });
    const onMessage = (msg) => {
      if (msg.appointment_id !== appointmentId) return;
      setMessages((list) => merge(list, [msg]));
      setPeerTyping(false);
    };
    const onTyping = ({ appointment_id, typing }) => {
      if (appointment_id !== appointmentId) return;
      setPeerTyping(typing);
      clearTimeout(typingTimer.current);
      if (typing) typingTimer.current = setTimeout(() => setPeerTyping(false), 4000);
    };
    socket.on("chat:message", onMessage);
    socket.on("chat:typing", onTyping);
    return () => {
      off();
      socket.off("chat:message", onMessage);
      socket.off("chat:typing", onTyping);
    };
  }, [socket, onConnect, appointmentId, enabled, deliver]);

  const send = useCallback(
    (body) => {
      const item = { body, idempotency_key: crypto.randomUUID(), created_at: new Date().toISOString() };
      outbox.current = [...outbox.current, item];
      persistOutbox();
      setMessages((list) => [...list, { ...item, id: item.idempotency_key, sender_id: myId, status: "sending" }]);
      if (socket?.connected) deliver(socket, item);
      socket?.emit("chat:typing", { appointment_id: appointmentId, typing: false });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [socket, deliver, appointmentId, myId]
  );

  const retry = useCallback(
    (key) => {
      const failed = messages.find((m) => m.idempotency_key === key);
      if (!failed) return;
      setMessages((list) => list.filter((m) => m.idempotency_key !== key));
      send(failed.body);
    },
    [messages, send]
  );

  const typing = useCallback(() => {
    const now = Date.now();
    if (!socket?.connected || now - lastTypingSent.current < 2500) return;
    lastTypingSent.current = now;
    socket.emit("chat:typing", { appointment_id: appointmentId, typing: true });
  }, [socket, appointmentId]);

  return { messages, send, retry, typing, peerTyping };
}
