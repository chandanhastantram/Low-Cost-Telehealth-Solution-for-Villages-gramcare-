import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, storeSession } from "../api";

// OTP is disabled for now — one click logs into a fixed demo account per
// role so the app can be demoed without needing to read the backend
// console for a code. Re-enable the real phone+OTP form below when ready.
const DEMO_ROLES = [
  { role: "patient", label: "Patient", blurb: "Book consultations, view records" },
  { role: "doctor", label: "Doctor", blurb: "Review cases, run consultations" },
  { role: "admin", label: "Admin", blurb: "Onboard staff, manage facilities" },
];

export default function Login() {
  const [loadingRole, setLoadingRole] = useState(null);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function loginAs(role) {
    setError("");
    setLoadingRole(role);
    try {
      const { data } = await api.post(`/auth/dev-login?role=${role}`);
      storeSession(data);
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not log in.");
    } finally {
      setLoadingRole(null);
    }
  }

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <h1>GramCare</h1>
        <p className="subtitle">Village telehealth — choose a demo account</p>

        <div className="role-picker">
          {DEMO_ROLES.map(({ role, label, blurb }) => (
            <button
              key={role}
              className="role-option"
              onClick={() => loginAs(role)}
              disabled={loadingRole !== null}
            >
              <strong>{label}</strong>
              <span>{blurb}</span>
              {loadingRole === role && <em>Logging in…</em>}
            </button>
          ))}
        </div>

        {error && <p className="error">{error}</p>}
        <p className="hint">OTP login is temporarily disabled for demo purposes.</p>
      </div>
    </div>
  );
}
