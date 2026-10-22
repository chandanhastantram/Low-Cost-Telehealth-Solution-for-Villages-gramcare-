import { useState } from "react";
import { Link } from "react-router-dom";
import { Activity, Droplets, HeartPulse, Plus, Send, Siren, Thermometer, Trash2, Wind } from "lucide-react";
import { api, getStoredUser } from "../api";
import { errorText } from "../lib/copy";
import { Alert, Button, Card, Field, Stamp } from "../ui/kit";
import { useToast } from "../ui/toast";

// Normal ranges only drive the red outline as you type — the server's
// rule engine is what actually flags a case.
const VITALS = [
  { key: "temperature_c", label: "Temp", unit: "°C", icon: Thermometer, step: "0.1", ok: (v) => v >= 35 && v <= 38.5 },
  { key: "pulse_bpm", label: "Pulse", unit: "bpm", icon: HeartPulse, ok: (v) => v >= 50 && v <= 120 },
  { key: "spo2_pct", label: "SpO₂", unit: "%", icon: Droplets, ok: (v) => v >= 92 },
  { key: "bp_systolic", label: "BP sys", unit: "mmHg", icon: Activity, ok: (v) => v >= 90 && v <= 160 },
  { key: "bp_diastolic", label: "BP dia", unit: "mmHg", icon: Activity, ok: (v) => v >= 55 && v <= 100 },
  { key: "respiratory_rate", label: "Breaths", unit: "/min", icon: Wind, ok: (v) => v >= 10 && v <= 24 },
];

const SYMPTOMS = [
  { key: "fever", label: "Fever" },
  { key: "cough", label: "Cough" },
  { key: "chest_pain", label: "Chest pain" },
  { key: "difficulty_breathing", label: "Hard to breathe" },
  { key: "severe_headache", label: "Severe headache" },
  { key: "vomiting", label: "Vomiting" },
  { key: "diarrhoea", label: "Diarrhoea" },
  { key: "loss_of_consciousness", label: "Fainted" },
  { key: "rash", label: "Rash" },
  { key: "pregnant", label: "Pregnant" },
];

function TriageCard({ result }) {
  const level = result.urgent ? "red" : result.flags.length ? "orange" : "green";
  return (
    <div className="triage">
      <div className="lights" data-level={level} aria-label={`Triage: ${level}`}>
        <i />
        <i />
        <i />
      </div>
      <div>
        <p className="triage-summary">{(result.summary || "").replace(/^\[ADVICE ONLY[^\]]*\]\s*/, "").replace(/^⚠️\s*/, "")}</p>
        {result.flags.map((f) => (
          <div key={f.rule_name} className={`flag flag-${f.severity}`}>
            <strong>{f.rule_name}</strong>
            <span>{f.advice}</span>
          </div>
        ))}
        <p className="advice-only">Advice only · not a diagnosis · a doctor decides</p>
      </div>
    </div>
  );
}

const emptyMed = () => ({ name: "", dose: "", frequency: "", duration: "" });

function PrescriptionForm({ encounterId, onSaved }) {
  const [meds, setMeds] = useState([emptyMed()]);
  const [advice, setAdvice] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = (i, key, value) => setMeds((m) => m.map((x, j) => (j === i ? { ...x, [key]: value } : x)));

  async function save(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post(`/encounters/${encounterId}/prescriptions`, {
        medications: meds.filter((m) => m.name.trim()),
        advice: advice || undefined,
        follow_up_date: followUp ? new Date(followUp).toISOString() : undefined,
        idempotency_key: crypto.randomUUID(),
      });
      onSaved(data);
    } catch (err) {
      setError(errorText(err, "Could not save the prescription."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save}>
      <div className="rx-head" style={{ marginBottom: "0.8rem" }}>
        <span className="rx-symbol">℞</span> Prescription
      </div>
      {meds.map((m, i) => (
        <div className="med-row" key={i}>
          <input placeholder="Medicine" value={m.name} onChange={(e) => update(i, "name", e.target.value)} required={i === 0} />
          <input placeholder="Dose" value={m.dose} onChange={(e) => update(i, "dose", e.target.value)} required={Boolean(m.name)} />
          <input placeholder="How often" value={m.frequency} onChange={(e) => update(i, "frequency", e.target.value)} required={Boolean(m.name)} />
          <input placeholder="How long" value={m.duration} onChange={(e) => update(i, "duration", e.target.value)} required={Boolean(m.name)} />
          <button
            type="button"
            className="icon-btn"
            aria-label="Remove medicine"
            onClick={() => setMeds((x) => (x.length === 1 ? [emptyMed()] : x.filter((_, j) => j !== i)))}
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <Button type="button" variant="ghost" size="sm" icon={Plus} onClick={() => setMeds((m) => [...m, emptyMed()])}>
        Add medicine
      </Button>
      <div className="form-grid" style={{ marginTop: "0.9rem" }}>
        <Field label="Advice (said out loud to the patient)" className="span-2">
          {(id) => <textarea id={id} rows={2} value={advice} onChange={(e) => setAdvice(e.target.value)} />}
        </Field>
        <Field label="Follow up on">
          {(id) => <input id={id} type="date" value={followUp} onChange={(e) => setFollowUp(e.target.value)} />}
        </Field>
      </div>
      <Alert onClose={() => setError("")}>{error}</Alert>
      <Button loading={busy}>Sign &amp; save prescription</Button>
    </form>
  );
}

export default function ClinicalPanel({ appointment }) {
  const user = getStoredUser();
  const toast = useToast();
  const canRecord = user?.role === "chw" || user?.role === "admin" || user?.role === "doctor";
  const canPrescribe = user?.role === "doctor" || user?.role === "admin";

  const [vitals, setVitals] = useState({});
  const [symptoms, setSymptoms] = useState({});
  const [complaint, setComplaint] = useState("");
  const [triage, setTriage] = useState(null);
  const [encounter, setEncounter] = useState(null);
  const [rx, setRx] = useState(null);
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  if (!canRecord) return null;

  const setVital = (key, value) => setVitals((v) => ({ ...v, [key]: value === "" ? undefined : Number(value) }));
  const toggleSymptom = (key) => setSymptoms((s) => ({ ...s, [key]: !s[key] }));
  const chosenSymptoms = Object.fromEntries(Object.entries(symptoms).filter(([, v]) => v));

  async function runTriage() {
    setError("");
    setBusy("triage");
    try {
      const { data } = await api.post("/triage/evaluate", { symptoms: chosenSymptoms, vitals });
      setTriage(data);
      if (data.urgent) toast("Red flag — consider referral now.", "red");
    } catch (err) {
      setError(errorText(err, "Triage check failed."));
    } finally {
      setBusy("");
    }
  }

  async function saveEncounter() {
    setError("");
    setBusy("save");
    try {
      const { data } = await api.post("/encounters", {
        patient_id: appointment.patient_id,
        appointment_id: appointment.id,
        encounter_date: new Date().toISOString(),
        chief_complaint: complaint || undefined,
        symptoms_json: Object.keys(chosenSymptoms).length ? chosenSymptoms : undefined,
        consultation_mode: appointment.consultation_mode,
        vitals,
        idempotency_key: crypto.randomUUID(),
      });
      setEncounter(data);
      if (data.triage_flags) setTriage(data.triage_flags);
    } catch (err) {
      setError(errorText(err, "Could not save the visit."));
    } finally {
      setBusy("");
    }
  }

  async function sendCase() {
    setError("");
    setBusy("send");
    try {
      await api.post("/teleconsult/store-forward", {
        encounter_id: encounter.id,
        patient_id: appointment.patient_id,
        payload_json: { chief_complaint: complaint, vitals, symptoms: Object.keys(chosenSymptoms), triage },
        idempotency_key: `sf-${encounter.id}`,
      });
      setSent(true);
      toast("Case sent. You'll find the doctor's reply under My cases.");
    } catch (err) {
      setError(errorText(err, "Could not send the case."));
    } finally {
      setBusy("");
    }
  }

  return (
    <Card ruled>
      <div className="card-head">
        <h2>Visit notes</h2>
        <Link className="link-btn" to={`/patients/${appointment.patient_id}/records`}>
          Past visits →
        </Link>
      </div>
      <Alert onClose={() => setError("")}>{error}</Alert>

      {!encounter ? (
        <>
          <Field label="What brings them in today?">
            {(id) => (
              <textarea id={id} rows={2} value={complaint} onChange={(e) => setComplaint(e.target.value)} placeholder="In their words — “fever for three days, can't eat”" />
            )}
          </Field>

          <p className="eyebrow">Vitals</p>
          <div className="vitals">
            {VITALS.map((v) => {
              const value = vitals[v.key];
              const off = value != null && !v.ok(value);
              return (
                <div key={v.key} className={`vital ${off ? "is-off" : ""}`}>
                  <label htmlFor={`v-${v.key}`}>
                    <v.icon size={14} /> {v.label}
                  </label>
                  <div className="vital-input">
                    <input
                      id={`v-${v.key}`}
                      type="number"
                      inputMode="decimal"
                      step={v.step || "1"}
                      value={value ?? ""}
                      onChange={(e) => setVital(v.key, e.target.value)}
                      placeholder="—"
                    />
                    <small>{v.unit}</small>
                  </div>
                </div>
              );
            })}
          </div>

          <p className="eyebrow">Symptoms (tap all that apply)</p>
          <div className="symptom-chips">
            {SYMPTOMS.map((s) => (
              <button key={s.key} type="button" className={`chip ${symptoms[s.key] ? "is-on" : ""}`} onClick={() => toggleSymptom(s.key)} aria-pressed={Boolean(symptoms[s.key])}>
                {s.label}
              </button>
            ))}
          </div>

          {triage && <TriageCard result={triage} />}

          <div className="form-actions">
            <Button variant="secondary" icon={Siren} onClick={runTriage} loading={busy === "triage"}>
              Check red flags
            </Button>
            <Button onClick={saveEncounter} loading={busy === "save"}>
              Save visit
            </Button>
          </div>
        </>
      ) : (
        <div style={{ position: "relative" }}>
          <Stamp className="stamp-corner">Recorded</Stamp>
          <p className="muted" style={{ marginBottom: "1rem", maxWidth: "42ch" }}>
            Visit written in the register{complaint ? `: “${complaint}”` : ""}. Red flags were checked automatically.
          </p>
          {triage && <TriageCard result={triage} />}

          {user?.role === "chw" && (
            <div className="form-actions" style={{ marginBottom: "1rem" }}>
              {sent ? (
                <Stamp tone="orange">Sent to queue</Stamp>
              ) : (
                <Button variant="accent" icon={Send} onClick={sendCase} loading={busy === "send"}>
                  Call not possible? Send the case
                </Button>
              )}
            </div>
          )}

          {canPrescribe &&
            (rx ? (
              <div className="rx" style={{ position: "relative" }}>
                <Stamp className="stamp-corner">Signed</Stamp>
                <div className="rx-head">
                  <span className="rx-symbol">℞</span> Prescription
                </div>
                <ul>
                  {rx.medications.map((m, i) => (
                    <li key={i}>
                      {m.name} — {m.dose}, {m.frequency}, {m.duration}
                    </li>
                  ))}
                </ul>
                {rx.advice && <p className="muted" style={{ marginTop: "0.4rem" }}>{rx.advice}</p>}
              </div>
            ) : (
              <PrescriptionForm encounterId={encounter.id} onSaved={setRx} />
            ))}
        </div>
      )}
    </Card>
  );
}
