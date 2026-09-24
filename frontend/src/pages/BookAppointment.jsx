import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import Layout from "../components/Layout";

export default function BookAppointment() {
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = location.state || {};

  const [doctors, setDoctors] = useState([]);
  const [patients, setPatients] = useState([]);
  const [patientSearch, setPatientSearch] = useState("");
  const [patientId, setPatientId] = useState(prefill.patientId || "");
  const [doctorId, setDoctorId] = useState("");
  const [dateTime, setDateTime] = useState("");
  const [mode, setMode] = useState("live_audio");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/doctors").then(({ data }) => setDoctors(data));
  }, []);

  useEffect(() => {
    const handle = setTimeout(() => {
      // PatientProfileResponse has no name/phone (only user_id) — join with
      // the user list client-side so the dropdown can show real names.
      Promise.all([
        api.get("/patients", { params: { search: patientSearch || undefined, per_page: 50 } }),
        api.get("/users", { params: { role: "patient", per_page: 200 } }),
      ]).then(([{ data: patientData }, { data: userData }]) => {
        const usersById = new Map(userData.items.map((u) => [u.id, u]));
        setPatients(
          (patientData.items || []).map((p) => ({
            ...p,
            name: usersById.get(p.user_id)?.name,
            phone: usersById.get(p.user_id)?.phone,
          }))
        );
      });
    }, 250);
    return () => clearTimeout(handle);
  }, [patientSearch]);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await api.post("/appointments", {
        patient_id: patientId,
        doctor_id: doctorId,
        scheduled_at: new Date(dateTime).toISOString(),
        consultation_mode: mode,
      });
      setStatus("Booked!");
      navigate(`/appointment/${data.id}`);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not book appointment.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Layout>
      <div className="page">
        <header className="page-header">
          <h2>Book appointment</h2>
        </header>

        <form className="form-card" onSubmit={submit}>
          <label>Find patient</label>
          <input
            value={patientSearch}
            onChange={(e) => setPatientSearch(e.target.value)}
            placeholder="Search by name…"
          />
          <select value={patientId} onChange={(e) => setPatientId(e.target.value)} required>
            <option value="">Select a patient</option>
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name || `Patient ${p.id.slice(0, 8)}…`}
                {p.phone ? ` · ${p.phone}` : ""}
              </option>
            ))}
          </select>
          {patients.length === 0 && (
            <p className="hint">No patients found — register one first.</p>
          )}

          <label>Doctor</label>
          <select value={doctorId} onChange={(e) => setDoctorId(e.target.value)} required>
            <option value="">Select a doctor</option>
            {doctors.map((d) => (
              <option key={d.id} value={d.id}>
                Dr. {d.name} {d.specialization ? `— ${d.specialization}` : ""}
              </option>
            ))}
          </select>

          <label>Date & time</label>
          <input type="datetime-local" value={dateTime} onChange={(e) => setDateTime(e.target.value)} required />

          <label>Consultation mode</label>
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="live_audio">Live audio (default — low bandwidth)</option>
            <option value="live_video">Live video</option>
            <option value="store_forward">Store &amp; forward</option>
          </select>

          {status && !error && <p className="hint">{status}</p>}
          {error && <p className="error">{error}</p>}

          <button className="button" type="submit" disabled={loading}>
            {loading ? "Booking…" : "Book appointment"}
          </button>
        </form>
      </div>
    </Layout>
  );
}
