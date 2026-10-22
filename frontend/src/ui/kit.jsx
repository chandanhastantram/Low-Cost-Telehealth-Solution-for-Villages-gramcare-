import { useEffect, useId, useRef, useState } from "react";
import { X } from "lucide-react";
import { LOADING_LINES } from "../lib/copy";
import { Banyan, Goat, Lantern, Toran } from "./doodles";

export function Button({ variant = "primary", size, icon: Icon, loading, children, className = "", ...props }) {
  return (
    <button
      className={`btn btn-${variant} ${size ? `btn-${size}` : ""} ${loading ? "is-loading" : ""} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Spinner /> : Icon && <Icon size={size === "sm" ? 15 : 17} strokeWidth={2.2} />}
      {children && <span>{children}</span>}
    </button>
  );
}

export function IconButton({ icon: Icon, label, className = "", ...props }) {
  return (
    <button className={`icon-btn ${className}`} aria-label={label} data-tip={label} {...props}>
      <Icon size={18} strokeWidth={2.1} />
    </button>
  );
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />;
}

export function Card({ as: Tag = "section", ruled, className = "", children, ...props }) {
  return (
    <Tag className={`card ${ruled ? "card-ruled" : ""} ${className}`} {...props}>
      {children}
    </Tag>
  );
}

export function Field({ label, hint, error, children, className = "" }) {
  const id = useId();
  const child = typeof children === "function" ? children(id) : children;
  return (
    <div className={`field ${error ? "has-error" : ""} ${className}`}>
      {label && <label htmlFor={id}>{label}</label>}
      {child}
      {error ? <p className="field-error">{error}</p> : hint && <p className="field-hint">{hint}</p>}
    </div>
  );
}

export function Badge({ tone = "neutral", children, dot }) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <i className="badge-dot" />}
      {children}
    </span>
  );
}

const STATUS_TONE = {
  pending: "orange",
  confirmed: "green",
  completed: "ink",
  cancelled: "neutral",
  no_show: "red",
  queued: "orange",
  replied: "green",
};

export function StatusBadge({ status }) {
  return (
    <Badge tone={STATUS_TONE[status] || "neutral"} dot>
      {status?.replace("_", " ")}
    </Badge>
  );
}

/** The rubber stamp that thumps onto a card when something is saved. */
export function Stamp({ children, tone = "green", className = "" }) {
  return <span className={`stamp stamp-${tone} ${className}`}>{children}</span>;
}

export function Alert({ tone = "red", children, onClose }) {
  if (!children) return null;
  return (
    <div className={`alert alert-${tone}`} role={tone === "red" ? "alert" : "status"}>
      <span>{children}</span>
      {onClose && (
        <button className="alert-close" onClick={onClose} aria-label="Dismiss">
          <X size={15} />
        </button>
      )}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.value}
          role="tab"
          aria-selected={value === t.value}
          className={`tab ${value === t.value ? "is-active" : ""}`}
          onClick={() => onChange(t.value)}
        >
          {t.icon && <t.icon size={16} />}
          {t.label}
          {t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented({ options, value, onChange, name }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <button
          type="button"
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          className={value === o.value ? "is-active" : ""}
          onClick={() => onChange(o.value)}
        >
          {o.icon && <o.icon size={16} />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ lines = 3 }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton" style={{ "--i": i }} />
      ))}
    </div>
  );
}

/** Skeleton plus a rotating line of village-flavoured loading copy. */
export function Loading({ lines = 3 }) {
  const [idx, setIdx] = useState(() => Math.floor(Math.random() * LOADING_LINES.length));
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % LOADING_LINES.length), 2200);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="loading" role="status">
      <p className="loading-line" key={idx}>{LOADING_LINES[idx]}</p>
      <Skeleton lines={lines} />
    </div>
  );
}

const DOODLES = { goat: Goat, lantern: Lantern, banyan: Banyan };

export function EmptyState({ title, body, doodle = "goat", action }) {
  const Doodle = DOODLES[doodle] || Goat;
  return (
    <div className="empty">
      <Doodle />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

export function Avatar({ name = "?", size = 36 }) {
  const initials = name
    .replace(/^(dr\.?\s+)/i, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();
  // Stable hue-free tone choice from the name, using the standard palette only.
  const tones = ["green", "orange", "ink", "red"];
  const tone = tones[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % tones.length];
  return (
    <span className={`avatar avatar-${tone}`} style={{ width: size, height: size, fontSize: size * 0.38 }}>
      {initials || "?"}
    </span>
  );
}

export function PageHeader({ eyebrow, title, children, garland = true }) {
  return (
    <header className="page-header">
      {garland && <Toran />}
      <div className="page-header-row">
        <div>
          {eyebrow && <p className="eyebrow">{eyebrow}</p>}
          <h1>{title}</h1>
        </div>
        {children && <div className="page-actions">{children}</div>}
      </div>
    </header>
  );
}

export function StatTile({ label, value, icon: Icon, tone = "green", note, style }) {
  return (
    <div className={`stat stat-${tone}`} style={style}>
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {Icon && <Icon size={18} />}
      </div>
      <strong className="stat-value">{value}</strong>
      {note && <span className="stat-note">{note}</span>}
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={ref} className="modal" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}>
      <div className="modal-body">
        <div className="modal-head">
          <h2>{title}</h2>
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
        {children}
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </dialog>
  );
}

export function Kbd({ children }) {
  return <kbd className="kbd">{children}</kbd>;
}
