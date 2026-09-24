import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import Layout from "../components/Layout";

export default function PatientRecords() {
  const { id: patientId } = useParams();
  const [encounters, setEncounters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/patients/${patientId}/records`)
      .then(({ data }) => setEncounters(data.encounters || []))
      .catch((err) => setError(err.response?.data?.detail || "Could not load records."))
      .finally(() => setLoading(false));
  }, [patientId]);

  return (
    <Layout>
      <div className="page">
        <header className="page-header">
          <h2>Patient record</h2>
        </header>

        {loading && <p>Loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && encounters.length === 0 && <p className="empty">No encounters recorded yet.</p>}

        <div className="timeline">
          {encounters.map((enc) => (
            <div key={enc.id} className="timeline-card">
              <div className="timeline-date">{new Date(enc.encounter_date).toLocaleString()}</div>
              {enc.chief_complaint && <p>{enc.chief_complaint}</p>}
              <div className="vitals-row">
                {enc.temperature_c != null && <span>Temp {enc.temperature_c}°C</span>}
                {enc.pulse_bpm != null && <span>Pulse {enc.pulse_bpm}</span>}
                {enc.spo2_pct != null && <span>SpO2 {enc.spo2_pct}%</span>}
                {enc.bp_systolic != null && (
                  <span>
                    BP {enc.bp_systolic}/{enc.bp_diastolic}
                  </span>
                )}
              </div>
              {enc.triage_flags?.urgent && <div className="flag flag-red">Flagged urgent at time of visit</div>}
              {(enc.prescriptions || []).map((rx) => (
                <div key={rx.id} className="prescription">
                  <strong>Prescription</strong>
                  <ul>
                    {rx.medications.map((m, i) => (
                      <li key={i}>
                        {m.name} — {m.dose}, {m.frequency}, {m.duration}
                      </li>
                    ))}
                  </ul>
                  {rx.advice && <p className="meta">Advice: {rx.advice}</p>}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
