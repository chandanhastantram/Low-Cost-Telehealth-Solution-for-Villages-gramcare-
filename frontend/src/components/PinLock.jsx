import { useEffect, useState } from "react";
import { Delete } from "lucide-react";
import { checkLocalPin } from "../lib/pin";
import { getStoredUser } from "../api";
import { Lantern } from "../ui/doodles";
import ThemeToggle from "./ThemeToggle";

const PIN_LENGTH = 4;

/** Full-screen keypad. Works with no network — the PIN is checked on-device. */
export default function PinLock({ onUnlock, onForgot }) {
  const user = getStoredUser();
  const [pin, setPin] = useState("");
  const [wrong, setWrong] = useState(false);
  const [message, setMessage] = useState("Enter your PIN to open the register");

  useEffect(() => {
    if (pin.length < PIN_LENGTH) return;
    let cancelled = false;
    checkLocalPin(pin).then(({ ok, remaining }) => {
      if (cancelled) return;
      if (ok) return onUnlock();
      if (remaining === 0) return onForgot("Too many wrong PINs — please log in again.");
      setWrong(true);
      setMessage(`Not quite. ${remaining} ${remaining === 1 ? "try" : "tries"} left.`);
      setTimeout(() => {
        setWrong(false);
        setPin("");
      }, 450);
    });
    return () => {
      cancelled = true;
    };
  }, [pin, onUnlock, onForgot]);

  useEffect(() => {
    function onKey(e) {
      if (/^\d$/.test(e.key)) setPin((p) => (p.length < PIN_LENGTH ? p + e.key : p));
      if (e.key === "Backspace") setPin((p) => p.slice(0, -1));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const press = (d) => setPin((p) => (p.length < PIN_LENGTH ? p + d : p));

  return (
    <div className="lock">
      <div className="theme-float">
        <ThemeToggle />
      </div>
      <div className="lock-card">
        <Lantern size={64} />
        <h2>Welcome back, {user?.name?.split(" ")[0] || "friend"}</h2>
        <p className="muted">{message}</p>
        <div className={`pin-dots ${wrong ? "is-wrong" : ""}`}>
          {Array.from({ length: PIN_LENGTH }, (_, i) => (
            <i key={i} className={i < pin.length ? "on" : ""} />
          ))}
        </div>
        <div className="keypad">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((d) => (
            <button key={d} onClick={() => press(String(d))}>
              {d}
            </button>
          ))}
          <button className="kp-ghost" onClick={() => onForgot()}>
            Forgot?
          </button>
          <button onClick={() => press("0")}>0</button>
          <button className="kp-ghost" onClick={() => setPin((p) => p.slice(0, -1))} aria-label="Delete">
            <Delete size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}
