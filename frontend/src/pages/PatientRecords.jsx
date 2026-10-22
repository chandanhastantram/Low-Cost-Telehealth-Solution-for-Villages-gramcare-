import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Printer, TriangleAlert } from "lucide-react";
import { api } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { MODE_LABEL, fmtDay, fmtFull, relative } from "../lib/format";
import { patientLabel, usePeople } from "../lib/people";
import { Alert, Avatar, Badge, Button, Card, EmptyState, Loading, PageHeader } from "../ui/kit";

function age(dob) {
  if (!dob) return null;
  const years = Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 86_400_000));
  return years >= 0 ? `${years} yrs` : null;
}

export default function PatientRecords({ own = false }) {
  const params = useParams();
  const people = usePeople();
  const [profile, setProfile] = useState(null);
  const [encounters, setEncounters] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const prof = own ? (await api.get("/patients/me")).data : (await api.get(`/patients/${params.id}`)).data;
        if (!alive) return;
        setProfile(prof);
        const { data } = await api.get(`/patients/${prof.id}/records`);
        if (alive) setEncounters(data.encounters || []);
      } catch (err) {
        if (!alive) return;
        setError(errorText(err, "Could not load the records."));
        setEncounters([]);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [own, params.id]);

  const name = own ? "My health file" : profile ? patientLabel(people, profile.id) : "Patient file";

  return (
    <Layout>
      <PageHeader eyebrow={own ? "Your records" : "Patient file"} title={name}>
        <Button variant="secondary" icon={Printer} onClick={() => window.print()}>
          Print
        </Button>
      </PageHeader>
      <Alert onClose={() => setError("")}>{error}</Alert>

      <div className="grid-main">
        <div>
          {encounters === null ? (
            <Loading lines={4} />
          ) : encounters.length === 0 ? (
            <Card>
              <EmptyState doodle="banyan" {...EMPTY.records} />
            </Card>
          ) : (
            <div className="timeline">
              {encounters.map((enc, i) => {
                const urgent = enc.triage_flags?.urgent;
                return (
                  <div key={enc.id} className={`tl-item ${urgent ? "is-urgent" : ""}`}>
                    <Card style={{ "--i": i }}>
                      <div className="card-head" style={{ marginBottom: "0.4rem" }}>
                        <span className="tl-date">
                          {fmtFull(enc.encounter_date)} · {relative(enc.encounter_date)}
                        </span>
                        <span style={{ display: "flex", gap: "0.4rem" }}>
                          {urgent && (
                            <Badge tone="red">
                              <TriangleAlert size={12} /> red flag
                            </Badge>
                          )}
                          {enc.consultation_mode && <Badge>{MODE_LABEL[enc.consultation_mode]}</Badge>}
                        </span>
                      </div>
                      <h3>{enc.chief_complaint || "Routine visit"}</h3>
                      <div className="vital-pills">
                        {enc.temperature_c != null && <span className="vital-pill">Temp {enc.temperature_c}°C</span>}
                        {enc.pulse_bpm != null && <span className="vital-pill">Pulse {enc.pulse_bpm}</span>}
                        {enc.spo2_pct != null && <span className="vital-pill">O₂ {enc.spo2_pct}%</span>}
                        {enc.bp_systolic != null && (
                          <span className="vital-pill">
                            BP {enc.bp_systolic}/{enc.bp_diastolic ?? "–"}
                          </span>
                        )}
                        {enc.respiratory_rate != null && <span className="vital-pill">{enc.respiratory_rate} breaths/min</span>}
                      </div>
                      {enc.symptoms_json && Object.keys(enc.symptoms_json).length > 0 && (
                        <p className="muted" style={{ fontSize: "0.88rem" }}>
                          Symptoms: {Object.keys(enc.symptoms_json).map((s) => s.replaceAll("_", " ")).join(", ")}
                        </p>
                      )}
                      {(enc.prescriptions || []).map((rx) => (
                        <div key={rx.id} className="rx">
                          <div className="rx-head">
                            <span className="rx-symbol">℞</span> {fmtDay(rx.issued_at || rx.created_at)}
                          </div>
                          <ul>
                            {rx.medications.map((m, j) => (
                              <li key={j}>
                                <b>{m.name}</b> — {m.dose}, {m.frequency}, {m.duration}
                              </li>
                            ))}
                          </ul>
                          {rx.advice && <p className="muted" style={{ marginTop: "0.4rem" }}>“{rx.advice}”</p>}
                          {rx.follow_up_date && (
                            <p style={{ marginTop: "0.4rem", fontWeight: 600 }}>Come back: {fmtDay(rx.follow_up_date)}</p>
                          )}
                        </div>
                      ))}
                    </Card>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {profile && (
          <Card ruled style={{ position: "sticky", top: "1.5rem" }}>
            <div style={{ display: "flex", gap: "0.8rem", alignItems: "center", marginBottom: "1rem" }}>
              <Avatar name={own ? "Me" : patientLabel(people, profile.id)} size={48} />
              <div>
                <h3>{own ? "About you" : patientLabel(people, profile.id)}</h3>
                <span className="muted" style={{ fontSize: "0.85rem", textTransform: "capitalize" }}>
                  {[profile.gender, age(profile.date_of_birth)].filter(Boolean).join(" · ") || "Details not recorded"}
                </span>
              </div>
            </div>
            <div className="summary-ticket">
              <dl>
                <dt>Blood group</dt>
                <dd>{profile.blood_group || "—"}</dd>
                <dt>Allergies</dt>
                <dd>{profile.allergies || "None known"}</dd>
                <dt>Long-term</dt>
                <dd>{profile.chronic_conditions || "—"}</dd>
                <dt>Consent</dt>
                <dd>{profile.consent_recorded ? "Recorded ✓" : "Not recorded"}</dd>
                <dt>Visits</dt>
                <dd className="mono">{encounters?.length ?? "…"}</dd>
              </dl>
            </div>
          </Card>
        )}
      </div>
    </Layout>
  );
}
