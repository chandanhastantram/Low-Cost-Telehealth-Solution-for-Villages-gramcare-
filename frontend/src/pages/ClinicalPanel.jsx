import { useState } from "react";
import { Link } from "react-router-dom";
import { api, getStoredUser } from "../api";

const VITAL_FIELDS = [
  { key: "temperature_c", label: "Temp (°C)" },
  { key: "pulse_bpm", label: "Pulse (bpm)" },
  { key: "spo2_pct", label: "SpO2 (%)" },
  { key: "bp_systolic", label: "BP systolic" },
  { key: "bp_diastolic", label: "BP diastolic" },
];

export default function ClinicalPanel({ appointment }) {
  const user = getStoredUser();
  const isChwOrAdmin = user?.role === "chw" || user?.role === "admin";
  const isDoctorOrAdmin = user?.role === "doctor" || user?.role === "admin";

  const [vitals, setVitals] = useState({});
  const [complaint, setComplaint] = useState("");
  const [triageResult, setTriageResult] = useState(null);
  const [encounter, setEncounter] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [medName, setMedName] = useState("");
  const [medDose, setMedDose] = useState("");
  const [medFreq, setMedFreq] = useState("");
  const [medDuration, setMedDuration] = useState("");
  const [advice, setAdvice] = useState("");
  const [rxSaved, setRxSaved] = useState(false);

  function setVital(key, value) {
    setVitals((v) => ({ ...v, [key]: value === "" ? undefined : Number(value) }));
  }

  async function runTriage() {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/triage/evaluate", {
        symptoms: {},
        vitals,
      });
      setTriageResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Triage check failed.");
    } finally {
      setBusy(false);
    }
  }

  async function saveEncounter() {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/encounters", {
        patient_id: appointment.patient_id,
        appointment_id: appointment.id,
        encounter_date: new Date().toISOString(),
        chief_complaint: complaint || undefined,
        vitals,
        triage_flags: triageResult ? { flags: triageResult.flags, urgent: triageResult.urgent } : undefined,
      });
      setEncounter(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save the encounter.");
    } finally {
      setBusy(false);
    }
  }

  async function sendStoreForward() {
    setError("");
    setBusy(true);
    try {
      await api.post("/teleconsult/store-forward", {
        encounter_id: encounter.id,
        patient_id: appointment.patient_id,
        payload_json: { chief_complaint: complaint, vitals, triage: triageResult },
      });
      alert("Sent to the doctor's store-and-forward queue.");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not send store-and-forward case.");
    } finally {
      setBusy(false);
    }
  }

  async function savePrescription(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.post(`/encounters/${encounter.id}/prescriptions`, {
        medications: [
          { name: medName, dose: medDose, frequency: medFreq, duration: medDuration },
        ],
        advice: advice || undefined,
      });
      setRxSaved(true);
    } catch (err) {
      setError(err.response?.data?.detail || "Could not save the prescription.");
    } finally {
      setBusy(false);
    }
  }

  if (!isChwOrAdmin && !isDoctorOrAdmin) {
    return null; // patients don't record vitals or write prescriptions
  }

  return (
    <section className="clinical-panel">
      <h3>Clinical record</h3>
      {error && <p className="error">{error}</p>}

      {isChwOrAdmin && !encounter && (
        <div className="clinical-form">
          <label>Chief complaint</label>
          <textarea value={complaint} onChange={(e) => setComplaint(e.target.value)} rows={2} />

          <div className="vitals-grid">
            {VITAL_FIELDS.map((f) => (
              <div key={f.key}>
                <label>{f.label}</label>
                <input
                  type="number"
                  value={vitals[f.key] ?? ""}
                  onChange={(e) => setVital(f.key, e.target.value)}
                />
              </div>
            ))}
          </div>

          <div className="action-row">
            <button className="button secondary" type="button" onClick={runTriage} disabled={busy}>
              Run triage check
            </button>
            <button className="button" type="button" onClick={saveEncounter} disabled={busy}>
              Save encounter
            </button>
          </div>

          {triageResult && (
            <div className={`triage-result ${triageResult.urgent ? "urgent" : ""}`}>
              <p>{triageResult.summary}</p>
              {triageResult.flags.map((f) => (
                <div key={f.rule_name} className={`flag flag-${f.severity}`}>
                  <strong>{f.rule_name}</strong> — {f.advice}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {encounter && (
        <div className="encounter-saved">
          <p className="hint">Encounter recorded.</p>

          {user?.role === "chw" && (
            <button className="button secondary" onClick={sendStoreForward} disabled={busy}>
              Send as store-and-forward (if call isn't possible)
            </button>
          )}

          {isDoctorOrAdmin && !rxSaved && (
            <form className="clinical-form" onSubmit={savePrescription}>
              <h4>Write prescription</h4>
              <label>Medicine</label>
              <input value={medName} onChange={(e) => setMedName(e.target.value)} required />
              <label>Dose</label>
              <input value={medDose} onChange={(e) => setMedDose(e.target.value)} required />
              <label>Frequency</label>
              <input value={medFreq} onChange={(e) => setMedFreq(e.target.value)} required />
              <label>Duration</label>
              <input value={medDuration} onChange={(e) => setMedDuration(e.target.value)} required />
              <label>Advice</label>
              <textarea value={advice} onChange={(e) => setAdvice(e.target.value)} rows={2} />
              <button className="button" type="submit" disabled={busy}>
                Save prescription
              </button>
            </form>
          )}
          {rxSaved && <p className="hint">Prescription saved.</p>}

          <Link className="link" to={`/patients/${appointment.patient_id}/records`}>
            View full patient record
          </Link>
        </div>
      )}
    </section>
  );
}
