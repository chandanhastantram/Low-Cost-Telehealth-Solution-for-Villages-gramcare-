import { useState } from "react";
import { api, getStoredUser } from "../api";
import Layout from "../components/Layout";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिंदी (Hindi)" },
  { code: "kn", label: "ಕನ್ನಡ (Kannada)" },
];

export default function Profile() {
  const storedUser = getStoredUser();
  const [name, setName] = useState(storedUser?.name || "");
  const [language, setLanguage] = useState("en");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function save(e) {
    e.preventDefault();
    setError("");
    setStatus("");
    setLoading(true);
    try {
      const { data } = await api.patch("/users/me", { name, language_code: language });
      const current = JSON.parse(localStorage.getItem("user") || "{}");
      localStorage.setItem("user", JSON.stringify({ ...current, name: data.name }));
      setStatus("Saved.");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not update profile.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="page">
        <header className="page-header">
          <h2>Your profile</h2>
        </header>

        <form className="form-card" onSubmit={save}>
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required />

          <label>Preferred language</label>
          <select value={language} onChange={(e) => setLanguage(e.target.value)}>
            {LANGUAGES.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </select>
          <p className="hint">
            Prescriptions and reminders are designed to be read aloud in this language for
            low-literacy users.
          </p>

          <label>Role</label>
          <input value={storedUser?.role} disabled />

          {status && !error && <p className="hint">{status}</p>}
          {error && <p className="error">{error}</p>}

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Saving…" : "Save changes"}
          </button>
        </form>
      </div>
    </Layout>
  );
}
