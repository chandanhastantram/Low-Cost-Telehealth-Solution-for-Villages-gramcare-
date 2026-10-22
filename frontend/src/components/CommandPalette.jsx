import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coffee, Lock, LogOut, Search, SunMoon } from "lucide-react";
import { getStoredUser } from "../api";
import { navFor } from "../lib/nav";
import { useTheme } from "../theme";
import { Kbd } from "../ui/kit";

/** Ctrl/⌘ + K quick jump. Opened from the sidebar hint too. */
export default function CommandPalette({ open, onClose, onLock, onLogout, onChai }) {
  const navigate = useNavigate();
  const { toggle } = useTheme();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const user = getStoredUser();

  const commands = useMemo(
    () => [
      ...navFor(user?.role).map((n) => ({ label: n.label, hint: n.hint, icon: n.icon, run: () => navigate(n.to) })),
      { label: "Switch theme", hint: "Daylight ↔ Lantern", icon: SunMoon, run: toggle },
      { label: "Lock the app", hint: "Needs your offline PIN", icon: Lock, run: onLock },
      { label: "Take a chai break", hint: "You deserve it", icon: Coffee, run: onChai },
      { label: "Log out", hint: "End this session", icon: LogOut, run: onLogout },
    ],
    [user?.role, navigate, toggle, onLock, onLogout, onChai]
  );

  const results = commands.filter((c) =>
    `${c.label} ${c.hint}`.toLowerCase().includes(query.trim().toLowerCase())
  );

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 10);
    }
  }, [open]);

  if (!open) return null;

  function run(cmd) {
    onClose();
    cmd?.run();
  }

  function onKey(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % Math.max(results.length, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % Math.max(results.length, 1));
    } else if (e.key === "Enter") {
      run(results[active]);
    } else if (e.key === "Escape") {
      onClose();
    }
  }

  return (
    <div className="palette" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette-box" role="dialog" aria-label="Quick jump">
        <div className="palette-input">
          <Search size={18} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onKey}
            placeholder="Where to? Try “book” or “theme”"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul className="palette-list">
          {results.length === 0 && <li className="palette-item muted">Nothing by that name in this village.</li>}
          {results.map((c, i) => (
            <li key={c.label}>
              <button
                className={`palette-item ${i === active ? "is-active" : ""}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => run(c)}
              >
                <c.icon size={17} />
                <span>{c.label}</span>
                <span className="muted" style={{ marginLeft: "auto", fontSize: "0.8rem" }}>
                  {c.hint}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="palette-foot">
          <span>
            <Kbd>↑</Kbd> <Kbd>↓</Kbd> move
          </span>
          <span>
            <Kbd>Enter</Kbd> open
          </span>
        </div>
      </div>
    </div>
  );
}
