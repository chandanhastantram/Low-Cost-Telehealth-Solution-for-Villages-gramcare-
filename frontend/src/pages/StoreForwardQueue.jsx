import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Inbox, Plus, RefreshCw, Trash2 } from "lucide-react";
import { api, getStoredUser } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { fmtFull, relative } from "../lib/format";
import { patientLabel, usePeople } from "../lib/people";
import { Alert, Button, Card, EmptyState, Field, Loading, PageHeader, Stamp, StatusBadge, Tabs } from "../ui/kit";
import { useToast } from "../ui/toast";

const VITAL_NAMES = {
  temperature_c: ["Temp", "°C"],
  pulse_bpm: ["Pulse", "bpm"],
  spo2_pct: ["SpO₂", "%"],
  bp_systolic: ["BP sys", ""],
  bp_diastolic: ["BP dia", ""],
  respiratory_rate: ["Breaths", "/min"],
};

function CaseFacts({ payload = {} }) {
  const vitals = Object.entries(payload.vitals || {}).filter(([, v]) => v != null);
  return (
    <>
      {payload.chief_complaint && (
        <p style={{ fontFamily: "var(--font-display)", fontSize: "1.1rem" }}>“{payload.chief_complaint}”</p>
      )}
      {vitals.length > 0 && (
        <div className="case-facts">
          {vitals.map(([k, v]) => (
            <div key={k} className="case-fact">
              <small>{VITAL_NAMES[k]?.[0] || k}</small>
              <span className="mono">
                {v} {VITAL_NAMES[k]?.[1]}
              </span>
            </div>
          ))}
        </div>
      )}
      {payload.symptoms?.length > 0 && (
        <div className="symptom-chips" style={{ margin: 0 }}>
          {payload.symptoms.map((s) => (
            <span key={s} className="chip is-on" style={{ cursor: "default" }}>
              {s.replaceAll("_", " ")}
            </span>
          ))}
        </div>
      )}
      {payload.triage?.urgent && (
        <Alert tone="red">Triage flagged this as urgent when it was sent.</Alert>
      )}
    </>
  );
}

const emptyMed = () => ({ name: "", dose: "", frequency: "", duration: "" });

function ReplyForm({ bundle, onDone }) {
  const toast = useToast();
  const [text, setText] = useState("");
  const [withRx, setWithRx] = useState(false);
  const [meds, setMeds] = useState([emptyMed()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const update = (i, key, value) => setMeds((m) => m.map((x, j) => (j === i ? { ...x, [key]: value } : x)));

  async function send(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const medications = meds.filter((m) => m.name.trim());
      const { data } = await api.post(`/teleconsult/store-forward/${bundle.id}/respond`, {
        response_text: text,
        prescription: withRx && medications.length ? { medications, idempotency_key: `sf-rx-${bundle.id}` } : undefined,
      });
      toast("Reply sent to the health worker.");
      onDone(data);
    } catch (err) {
      setError(errorText(err, "Could not send the reply."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={send}>
      <Field label="Your reply">
        {(id) => (
          <textarea id={id} rows={3} value={text} onChange={(e) => setText(e.target.value)} required placeholder="What should the health worker do next?" />
        )}
      </Field>
      <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginBottom: "0.8rem", cursor: "pointer" }}>
        <input type="checkbox" checked={withRx} onChange={(e) => setWithRx(e.target.checked)} /> Add a prescription
      </label>
      {withRx && (
        <>
          {meds.map((m, i) => (
            <div className="med-row" key={i}>
              <input placeholder="Medicine" value={m.name} onChange={(e) => update(i, "name", e.target.value)} required={i === 0} />
              <input placeholder="Dose" value={m.dose} onChange={(e) => update(i, "dose", e.target.value)} required={Boolean(m.name)} />
              <input placeholder="How often" value={m.frequency} onChange={(e) => update(i, "frequency", e.target.value)} required={Boolean(m.name)} />
              <input placeholder="How long" value={m.duration} onChange={(e) => update(i, "duration", e.target.value)} required={Boolean(m.name)} />
              <button type="button" className="icon-btn" aria-label="Remove" onClick={() => setMeds((x) => (x.length === 1 ? [emptyMed()] : x.filter((_, j) => j !== i)))}>
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          <Button type="button" variant="ghost" size="sm" icon={Plus} onClick={() => setMeds((m) => [...m, emptyMed()])}>
            Add medicine
          </Button>
        </>
      )}
      <Alert onClose={() => setError("")}>{error}</Alert>
      <div className="form-actions">
        <Button loading={busy}>Send reply</Button>
      </div>
    </form>
  );
}

function CaseCard({ bundle, index, people, canReply, onReplied }) {
  return (
    <Card ruled className="case" style={{ "--i": index }}>
      {bundle.status === "replied" && <Stamp className="stamp-corner">Answered</Stamp>}
      <div className="case-meta">
        <StatusBadge status={bundle.status} />
        <strong style={{ color: "var(--ink)" }}>{patientLabel(people, bundle.patient_id)}</strong>
        <span>· sent {relative(bundle.created_at)}</span>
      </div>
      <CaseFacts payload={bundle.payload_json || {}} />
      {bundle.doctor_response && (
        <div className="reply-note">
          <b>Doctor's reply</b> · {bundle.reviewed_at && fmtFull(bundle.reviewed_at)}
          <p style={{ marginTop: "0.3rem" }}>{bundle.doctor_response}</p>
          {bundle.prescription_id && <p className="muted" style={{ marginTop: "0.3rem" }}>℞ A prescription was added to the patient's file.</p>}
        </div>
      )}
      {canReply && bundle.status === "queued" && <ReplyForm bundle={bundle} onDone={onReplied} />}
      {bundle.status === "replied" && (
        <Link className="link-btn" to={`/patients/${bundle.patient_id}/records`}>
          Open patient file →
        </Link>
      )}
    </Card>
  );
}

export default function StoreForwardQueue() {
  const user = getStoredUser();
  const people = usePeople();
  const isChw = user?.role === "chw";
  const [tab, setTab] = useState(isChw ? "all" : "queued");
  const [bundles, setBundles] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setBundles(null);
    api
      .get("/teleconsult/store-forward", { params: tab === "all" ? {} : { status_filter: tab } })
      .then(({ data }) => setBundles(data))
      .catch((err) => {
        setError(errorText(err, "Could not load cases."));
        setBundles([]);
      });
  }, [tab]);

  useEffect(load, [load]);

  const tabs = isChw
    ? [
        { value: "all", label: "Everything" },
        { value: "queued", label: "Waiting" },
        { value: "replied", label: "Answered" },
      ]
    : [
        { value: "queued", label: "Waiting", icon: Inbox },
        { value: "replied", label: "Answered by me" },
      ];

  return (
    <Layout>
      <PageHeader eyebrow="Store & forward" title={isChw ? "Cases I've sent" : "The case queue"}>
        <Button variant="secondary" icon={RefreshCw} onClick={load}>
          Refresh
        </Button>
      </PageHeader>
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      <Alert onClose={() => setError("")}>{error}</Alert>
      {bundles === null ? (
        <Loading />
      ) : bundles.length === 0 ? (
        <Card>
          <EmptyState doodle={isChw ? "goat" : "lantern"} {...(isChw ? EMPTY.myCases : EMPTY.queue)} />
        </Card>
      ) : (
        <div className="stack">
          {bundles.map((b, i) => (
            <CaseCard
              key={b.id}
              bundle={b}
              index={i}
              people={people}
              canReply={!isChw}
              onReplied={(updated) =>
                setBundles((list) => (tab === "queued" ? list.filter((x) => x.id !== updated.id) : list.map((x) => (x.id === updated.id ? updated : x))))
              }
            />
          ))}
        </div>
      )}
    </Layout>
  );
}
