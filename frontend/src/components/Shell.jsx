import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { logout } from "../api";
import { CHAI_BREAK } from "../lib/copy";
import { hasLocalPin } from "../lib/pin";
import { useToast } from "../ui/toast";
import CommandPalette from "./CommandPalette";
import PinLock from "./PinLock";

const IDLE_LOCK_MS = 5 * 60 * 1000;
const UNLOCK_FLAG = "gc-unlocked";

const ShellContext = createContext(null);

export function useShell() {
  return useContext(ShellContext);
}

/** Wraps every signed-in page: auth guard, offline-PIN lock, Ctrl+K palette. */
export default function Shell() {
  const navigate = useNavigate();
  const toast = useToast();
  const signedIn = Boolean(localStorage.getItem("access_token"));
  const [locked, setLocked] = useState(() => hasLocalPin() && !sessionStorage.getItem(UNLOCK_FLAG));
  const [paletteOpen, setPaletteOpen] = useState(false);

  const lock = useCallback(() => {
    if (!hasLocalPin()) {
      toast("Set an offline PIN in Profile first, then you can lock the app.", "orange");
      return;
    }
    sessionStorage.removeItem(UNLOCK_FLAG);
    setLocked(true);
  }, [toast]);

  const unlock = useCallback(() => {
    sessionStorage.setItem(UNLOCK_FLAG, "1");
    setLocked(false);
  }, []);

  const signOut = useCallback(
    async (message) => {
      await logout();
      sessionStorage.removeItem(UNLOCK_FLAG);
      setLocked(false);
      if (typeof message === "string") toast(message, "orange");
      navigate("/login");
    },
    [navigate, toast]
  );

  const chai = useCallback(() => {
    toast(CHAI_BREAK[Math.floor(Math.random() * CHAI_BREAK.length)], "orange");
  }, [toast]);

  // Ctrl/⌘+K opens the palette; "/" too, when not typing.
  useEffect(() => {
    function onKey(e) {
      const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
      if ((e.key === "k" && (e.ctrlKey || e.metaKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Auto-lock after a few idle minutes, like a phone.
  useEffect(() => {
    if (locked) return;
    let timer;
    const reset = () => {
      clearTimeout(timer);
      timer = setTimeout(() => hasLocalPin() && lock(), IDLE_LOCK_MS);
    };
    const events = ["pointerdown", "keydown", "scroll"];
    events.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));
    reset();
    return () => {
      clearTimeout(timer);
      events.forEach((ev) => window.removeEventListener(ev, reset));
    };
  }, [locked, lock]);

  if (!signedIn) return <Navigate to="/login" replace />;
  if (locked) return <PinLock onUnlock={unlock} onForgot={signOut} />;

  return (
    <ShellContext.Provider value={{ openPalette: () => setPaletteOpen(true), lock, signOut, chai }}>
      <Outlet />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onLock={lock}
        onLogout={signOut}
        onChai={chai}
      />
    </ShellContext.Provider>
  );
}
