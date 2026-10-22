import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { HeartHandshake, KeyRound, ShieldCheck, Stethoscope, UserRound, Users } from "lucide-react";
import { api, storeSession } from "../api";
import ThemeToggle from "../components/ThemeToggle";
import { errorText } from "../lib/copy";
import { Alert, Button, Field, Tabs } from "../ui/kit";
import { Heartbeat, Logo } from "../ui/doodles";

const DEMO_ROLES = [
  { role: "chw", label: "Health worker", blurb: "Register villagers, take vitals, book consults", icon: HeartHandshake },
  { role: "doctor", label: "Doctor", blurb: "Run audio consults, answer queued cases", icon: Stethoscope },
  { role: "patient", label: "Patient", blurb: "See your visits and prescriptions", icon: UserRound },
  { role: "admin", label: "Admin", blurb: "Onboard staff, set up facilities", icon: ShieldCheck },
];

function DemoLogin({ onDone }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");

  async function loginAs(role) {
    setError("");
    setBusy(role);
    try {
      const { data } = await api.post("/auth/dev-login", null, { params: { role } });
      onDone(data);
    } catch (err) {
      setError(errorText(err, "Could not log in."));
      setBusy(null);
    }
  }

  return (
    <>
      <div className="role-cards">
        {DEMO_ROLES.map(({ role, label, blurb, icon: Icon }, i) => (
          <button key={role} className="role-card" style={{ "--i": i }} onClick={() => loginAs(role)} disabled={busy !== null}>
            <span className="rc-icon">
              <Icon size={20} />
            </span>
            <strong>{label}</strong>
            <span>{blurb}</span>
            {busy === role && <span className="spinner" />}
          </button>
        ))}
      </div>
      <Alert onClose={() => setError("")}>{error}</Alert>
      <p className="field-hint">Demo accounts only work while the server runs in debug mode.</p>
    </>
  );
}

function OtpLogin({ onDone }) {
  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("+91");
  const [name, setName] = useState("");
  const [needsName, setNeedsName] = useState(false);
  const [digits, setDigits] = useState(Array(6).fill(""));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const boxes = useRef([]);

  async function requestOtp(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.post("/auth/otp/request", { phone, name: name || undefined });
      setStep("code");
      setTimeout(() => boxes.current[0]?.focus(), 50);
    } catch (err) {
      if (err.response?.status === 400 && !name) {
        setNeedsName(true);
        setError("New number! Tell us your name so we can open a page in the register.");
      } else {
        setError(errorText(err, "Could not send the code."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function verify(code) {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/auth/otp/verify", { phone, otp: code });
      onDone(data);
    } catch (err) {
      setError(errorText(err, "That code didn't work."));
      setDigits(Array(6).fill(""));
      boxes.current[0]?.focus();
      setBusy(false);
    }
  }

  function typeDigit(i, value) {
    const clean = value.replace(/\D/g, "");
    if (clean.length > 1) {
      // Pasted the whole code
      const next = clean.slice(0, 6).split("");
      const filled = [...next, ...Array(6 - next.length).fill("")];
      setDigits(filled);
      if (next.length === 6) verify(next.join(""));
      return;
    }
    const next = digits.map((d, j) => (j === i ? clean : d));
    setDigits(next);
    if (clean && i < 5) boxes.current[i + 1]?.focus();
    if (next.every(Boolean)) verify(next.join(""));
  }

  if (step === "code") {
    return (
      <div>
        <p className="muted" style={{ marginBottom: "0.6rem" }}>
          We sent a 6-digit code to <b className="mono">{phone}</b>.
        </p>
        <div className="otp-boxes">
          {digits.map((d, i) => (
            <input
              key={i}
              ref={(el) => (boxes.current[i] = el)}
              value={d}
              inputMode="numeric"
              autoComplete={i === 0 ? "one-time-code" : "off"}
              aria-label={`Digit ${i + 1}`}
              onChange={(e) => typeDigit(i, e.target.value)}
              onKeyDown={(e) => e.key === "Backspace" && !d && i > 0 && boxes.current[i - 1]?.focus()}
              disabled={busy}
            />
          ))}
        </div>
        <Alert onClose={() => setError("")}>{error}</Alert>
        <div className="form-actions">
          <Button variant="ghost" onClick={() => setStep("phone")}>
            Change number
          </Button>
          {busy && <span className="muted">Checking…</span>}
        </div>
        <p className="field-hint" style={{ marginTop: "0.8rem" }}>
          In development the code is printed in the server console instead of an SMS.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={requestOtp}>
      <Field label="Mobile number">
        {(id) => <input id={id} value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" required />}
      </Field>
      {needsName && (
        <Field label="Your name">
          {(id) => <input id={id} value={name} onChange={(e) => setName(e.target.value)} required autoFocus />}
        </Field>
      )}
      <Alert tone={needsName ? "orange" : "red"} onClose={() => setError("")}>{error}</Alert>
      <Button className="btn-block" size="lg" loading={busy} icon={KeyRound}>
        Send me a code
      </Button>
    </form>
  );
}

export default function Login() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("demo");

  function done(data) {
    storeSession(data);
    navigate("/dashboard");
  }

  return (
    <div className="auth">
      <div className="theme-float">
        <ThemeToggle />
      </div>

      <section className="auth-story">
        <div className="brand" style={{ position: "relative", zIndex: 1 }}>
          <Logo size={40} />
          <div>
            <span className="brand-name">GramCare</span>
            <span className="brand-tag">village health register</span>
          </div>
        </div>
        <div style={{ position: "relative", zIndex: 1 }}>
          <h1>
            A doctor, one <em>phone call</em> away from every village.
          </h1>
          <Heartbeat />
          <p style={{ maxWidth: "46ch", opacity: 0.85 }}>
            Built for two bars of signal, shared phones and long walks. Records keep working when the
            network doesn't.
          </p>
        </div>
        <div className="auth-facts">
          <div>
            <strong>~30 kbps</strong>
            <span>is enough for a consult</span>
          </div>
          <div>
            <strong>0</strong>
            <span>paid SaaS services</span>
          </div>
          <div>
            <strong>
              <Users size={22} style={{ verticalAlign: "-3px" }} /> 4
            </strong>
            <span>roles, one register</span>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <h2>Open the register</h2>
          <p>Pick a demo account to look around, or sign in with your phone.</p>
          <Tabs
            value={mode}
            onChange={setMode}
            tabs={[
              { value: "demo", label: "Demo accounts" },
              { value: "otp", label: "Phone + code" },
            ]}
          />
          {mode === "demo" ? <DemoLogin onDone={done} /> : <OtpLogin onDone={done} />}
        </div>
      </section>
    </div>
  );
}
