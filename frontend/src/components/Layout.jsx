import { useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Command, Lock, LogOut } from "lucide-react";
import { getStoredUser } from "../api";
import { navFor } from "../lib/nav";
import { Avatar, IconButton, Kbd } from "../ui/kit";
import { Logo } from "../ui/doodles";
import SignalMeter from "./SignalMeter";
import ThemeToggle from "./ThemeToggle";
import { useShell } from "./Shell";

const ROLE_NAME = { patient: "Patient", chw: "Health worker", doctor: "Doctor", admin: "Admin" };

function Brand() {
  const { chai } = useShell();
  const clicks = useRef([]);
  const [wobble, setWobble] = useState(false);

  // Easter egg: tap the logo five times quickly for a chai break.
  function onClick() {
    const now = Date.now();
    clicks.current = [...clicks.current.filter((t) => now - t < 1500), now];
    setWobble(false);
    requestAnimationFrame(() => setWobble(true));
    if (clicks.current.length >= 5) {
      clicks.current = [];
      chai();
    }
  }

  return (
    <div className={`brand ${wobble ? "is-wobbling" : ""}`} onClick={onClick} onAnimationEnd={() => setWobble(false)}>
      <Logo />
      <div>
        <span className="brand-name">GramCare</span>
        <span className="brand-tag">village health register</span>
      </div>
    </div>
  );
}

export default function Layout({ children }) {
  const user = getStoredUser();
  const { openPalette, lock, signOut } = useShell();
  const items = navFor(user?.role);

  return (
    <div className="shell">
      <aside className="sidebar">
        <Brand />
        <button className="palette-hint" onClick={openPalette}>
          <span style={{ display: "inline-flex", gap: "0.45rem", alignItems: "center" }}>
            <Command size={14} /> Quick jump
          </span>
          <span>
            <Kbd>Ctrl</Kbd> <Kbd>K</Kbd>
          </span>
        </button>
        <nav className="nav" aria-label="Main">
          <span className="nav-label">Register</span>
          {items.map((item) => (
            <NavLink key={item.to + item.label} to={item.to} className="nav-link" end>
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="sidebar-tools">
            <SignalMeter />
            <ThemeToggle />
          </div>
          <Link to="/profile" className="user-chip">
            <Avatar name={user?.name} />
            <span className="user-chip-text">
              <strong>{user?.name}</strong>
              <span>{ROLE_NAME[user?.role] || user?.role}</span>
            </span>
          </Link>
          <div className="sidebar-tools">
            <IconButton icon={Lock} label="Lock app" onClick={lock} />
            <IconButton icon={LogOut} label="Log out" onClick={() => signOut()} />
          </div>
        </div>
      </aside>

      <header className="mobile-bar">
        <Link to="/dashboard" className="brand">
          <Logo size={30} />
          <span className="brand-name">GramCare</span>
        </Link>
        <div className="mobile-tools">
          <SignalMeter />
          <ThemeToggle />
          <IconButton icon={LogOut} label="Log out" onClick={() => signOut()} />
        </div>
      </header>

      <main className="main">
        <div className="main-inner">{children}</div>
      </main>

      <nav className="tabbar" aria-label="Main">
        {items.slice(0, 5).map((item) => (
          <NavLink key={item.to + item.label} to={item.to} end>
            <item.icon size={20} />
            {item.short}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
