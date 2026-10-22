import { useCallback, useEffect, useRef, useState } from "react";
import { io } from "socket.io-client";
import { api, SOCKET_URL } from "../api";

/**
 * One Socket.IO connection per consultation room, built for flaky links:
 * - long-polling fallback when websockets are blocked (default transports)
 * - endless reconnect with backoff
 * - the token is read on every (re)connect, and an expired one is refreshed
 * - `onConnect` callbacks re-join rooms after each reconnect
 */
export function useRoomSocket(enabled) {
  const [socket, setSocket] = useState(null);
  const [status, setStatus] = useState("connecting"); // connecting | online | offline
  const connectHandlers = useRef(new Set());

  useEffect(() => {
    if (!enabled) return;
    const s = io(SOCKET_URL, {
      auth: (cb) => cb({ token: localStorage.getItem("access_token") }),
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 8000,
      timeout: 15000,
    });

    s.on("connect", () => {
      setStatus("online");
      connectHandlers.current.forEach((fn) => fn(s));
    });
    s.on("disconnect", (reason) => {
      setStatus("offline");
      // Server-side kicks don't auto-reconnect; everything else does.
      if (reason === "io server disconnect") s.connect();
    });
    s.on("connect_error", async (err) => {
      setStatus("offline");
      if (/auth/i.test(err.message)) {
        try {
          await api.get("/users/me"); // axios interceptor refreshes the access token
          s.connect();
        } catch {
          /* refresh failed — the api layer sends the user to /login */
        }
      }
    });

    setSocket(s);
    return () => {
      s.removeAllListeners();
      s.disconnect();
      setSocket(null);
    };
  }, [enabled]);

  /** Register a callback for every (re)connect. Returns an unsubscribe fn. */
  const onConnect = useCallback(
    (fn) => {
      connectHandlers.current.add(fn);
      if (socket?.connected) fn(socket);
      return () => connectHandlers.current.delete(fn);
    },
    [socket]
  );

  return { socket, status, onConnect };
}
