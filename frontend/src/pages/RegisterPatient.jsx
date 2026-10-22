import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, CalendarPlus, Phone, UserPlus } from "lucide-react";
import { api } from "../api";
import Layout from "../components/Layout";
import { errorText } from "../lib/copy";
import { invalidatePeople } from "../lib/people";
import { Alert, Button, Card, Field, PageHeader, Segmented, Stamp } from "../ui/kit";

const GENDERS = [
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
  { value: "other", label: "Other" },
  { value: "", label: "Skip" },
];
const BLOOD = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

const STEPS = ["Who", "Consent", "Done"];

function Stepper({ step }) {
  return (
    <ol className="stepper">
      {STEPS.map((s, i) => (
        <li key={s} className={i < step ? "is-done" : i === step ? "is-active" : ""}>
          {s}
        </li>
      ))}
    </ol>
  );
}

export default function RegisterPatient() {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({
    phone: "+91",
    name: "",
    gender: "",
    dob: "",
    blood_group: "",
    allergies: "",
    emergency_contact_name: "",
    emergency_contact_phone: "",
  });
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e?.target ? e.target.value : e }));

  async function register() {
    setError("");
    setBusy(true);
    try {
      // 1. Make sure there's a user account for this phone (created on first contact).
      setStatus("Opening a page in the register…");
      try {
        await api.post("/auth/otp/request", { phone: form.phone, name: form.name });
      } catch (err) {
        if (err.response?.status !== 400 && err.response?.status !== 429) throw err;
      }
      // 2. Find it.
      setStatus("Finding the account…");
      const { data: users } = await api.get("/users", { params: { phone: form.phone } });
      const user = users.items.find((u) => u.phone === form.phone);
      if (!user) throw new Error("Couldn't find the account we just created. Check the number.");
      // 3. Patient profile, with consent recorded.
      setStatus("Writing the details…");
      const { data: profile } = await api.post("/patients", {
        user_id: user.id,
        gender: form.gender || undefined,
        date_of_birth: form.dob ? new Date(form.dob).toISOString() : undefined,
        blood_group: form.blood_group || undefined,
        allergies: form.allergies || undefined,
        emergency_contact_name: form.emergency_contact_name || undefined,
        emergency_contact_phone: form.emergency_contact_phone || undefined,
        consent_recorded: true,
        idempotency_key: crypto.randomUUID(),
      });
      invalidatePeople();
      setCreated({ ...profile, name: user.name });
      setStep(2);
    } catch (err) {
      setError(errorText(err, "Registration failed."));
    } finally {
      setStatus("");
      setBusy(false);
    }
  }

  return (
    <Layout>
      <PageHeader eyebrow="New entry" title="Register a villager" />
      <div className="grid-main">
        <Card ruled>
          <Stepper step={step} />

          {step === 0 && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setStep(1);
              }}
            >
              <div className="form-grid">
                <Field label="Mobile number" hint="Their own or a family member's">
                  {(id) => (
                    <div className="input-icon">
                      <Phone size={16} />
                      <input id={id} value={form.phone} onChange={set("phone")} inputMode="tel" pattern="\+?\d{10,14}" required />
                    </div>
                  )}
                </Field>
                <Field label="Full name">
                  {(id) => <input id={id} value={form.name} onChange={set("name")} required autoComplete="off" />}
                </Field>
                <Field label="Gender" className="span-2">
                  {() => <Segmented name="Gender" options={GENDERS} value={form.gender} onChange={set("gender")} />}
                </Field>
                <Field label="Date of birth" hint="Approximate is fine">
                  {(id) => <input id={id} type="date" value={form.dob} onChange={set("dob")} max={new Date().toISOString().slice(0, 10)} />}
                </Field>
                <Field label="Blood group">
                  {(id) => (
                    <select id={id} value={form.blood_group} onChange={set("blood_group")}>
                      {BLOOD.map((b) => (
                        <option key={b} value={b}>
                          {b || "Don't know"}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Known allergies" className="span-2">
                  {(id) => <input id={id} value={form.allergies} onChange={set("allergies")} placeholder="e.g. penicillin, none known" />}
                </Field>
                <Field label="Emergency contact">
                  {(id) => <input id={id} value={form.emergency_contact_name} onChange={set("emergency_contact_name")} placeholder="Name" />}
                </Field>
                <Field label="Their number">
                  {(id) => <input id={id} value={form.emergency_contact_phone} onChange={set("emergency_contact_phone")} inputMode="tel" />}
                </Field>
              </div>
              <div className="form-actions">
                <Button icon={ArrowRight}>Next: consent</Button>
              </div>
            </form>
          )}

          {step === 1 && (
            <div>
              <h3>Read this out loud to {form.name.split(" ")[0] || "them"}</h3>
              <blockquote
                style={{
                  margin: "0.9rem 0",
                  padding: "0.9rem 1rem",
                  borderLeft: "4px solid var(--orange)",
                  background: "var(--surface-2)",
                  borderRadius: "0 10px 10px 0",
                  fontFamily: "var(--font-display)",
                  fontSize: "1.05rem",
                }}
              >
                “Your health details will be written in GramCare so doctors can help you from far away.
                Only your health worker, your doctor and the clinic can see them. Nothing is shared with
                anyone else, and you can ask us to stop at any time.”
              </blockquote>
              <label style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", cursor: "pointer", margin: "1rem 0" }}>
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} style={{ marginTop: "0.3rem" }} />
                <span>
                  {form.name || "The patient"} understood and agreed. <span className="muted">(Consent is recorded with the time.)</span>
                </span>
              </label>
              <Alert onClose={() => setError("")}>{error}</Alert>
              {status && <p className="loading-line">{status}</p>}
              <div className="form-actions">
                <Button variant="ghost" icon={ArrowLeft} onClick={() => setStep(0)} disabled={busy}>
                  Back
                </Button>
                <Button icon={UserPlus} onClick={register} disabled={!consent} loading={busy}>
                  Register patient
                </Button>
              </div>
            </div>
          )}

          {step === 2 && created && (
            <div style={{ position: "relative", minHeight: 180 }}>
              <Stamp className="stamp-corner">Registered</Stamp>
              <h3>{created.name} is in the register</h3>
              <p className="muted" style={{ margin: "0.4rem 0 1.2rem", maxWidth: "40ch" }}>
                Their page is open. Next, find them a doctor — or register the next person in the queue.
              </p>
              <div className="form-actions">
                <Link className="btn btn-primary" to="/book" state={{ patientId: created.id, patientName: created.name }}>
                  <CalendarPlus size={17} /> Book a consult
                </Link>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setForm((f) => ({ ...f, phone: "+91", name: "", dob: "", allergies: "", emergency_contact_name: "", emergency_contact_phone: "" }));
                    setConsent(false);
                    setCreated(null);
                    setStep(0);
                  }}
                >
                  Register another
                </Button>
              </div>
            </div>
          )}
        </Card>

        <div className="stack">
          <Card className="tip">
            <UserPlus size={20} />
            <p>
              <b>Field note</b>
              Each number opens one page in the register. If a family shares one phone, register the
              second person with another relative's number and put the shared phone as their
              emergency contact.
            </p>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
