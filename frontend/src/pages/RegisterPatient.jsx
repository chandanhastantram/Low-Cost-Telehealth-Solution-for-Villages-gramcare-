import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import Layout from "../components/Layout";

export default function RegisterPatient() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [dob, setDob] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // Step 1: ensure a user account exists for this phone (creates one on
      // first contact, per the paper's CHW-assisted registration model —
      // the patient doesn't need to verify the OTP themselves right now).
      setStatus("Creating account…");
      try {
        await api.post("/auth/otp/request", { phone, name });
      } catch (err) {
        // 400 here usually just means the user already exists — fine.
        if (err.response?.status !== 400) throw err;
      }

      // Step 2: find that user's id.
      setStatus("Looking up account…");
      const { data: userList } = await api.get("/users", { params: { phone } });
      const match = userList.items.find((u) => u.phone === phone);
      if (!match) throw new Error("Could not find the account just created.");

      // Step 3: create the patient profile record.
      setStatus("Registering patient…");
      const { data: profile } = await api.post("/patients", {
        user_id: match.id,
        gender: gender || undefined,
        date_of_birth: dob ? new Date(dob).toISOString() : undefined,
      });

      setStatus("Recording consent…");
      await api.post(`/patients/${profile.id}/consent`);

      navigate("/book", { state: { patientId: profile.id, patientName: match.name } });
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Registration failed.");
      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="page">
        <header className="page-header">
          <h2>Register patient</h2>
        </header>

        <form className="form-card" onSubmit={submit}>
          <label>Patient phone number</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+919999000111" required />

          <label>Full name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required />

          <label>Gender</label>
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">Not specified</option>
            <option value="female">Female</option>
            <option value="male">Male</option>
            <option value="other">Other</option>
          </select>

          <label>Date of birth</label>
          <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} />

          {status && !error && <p className="hint">{status}</p>}
          {error && <p className="error">{error}</p>}

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Registering…" : "Register patient"}
          </button>
        </form>
      </div>
    </Layout>
  );
}
