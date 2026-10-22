import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { CalendarCheck2, Check, Headphones, Inbox, Search, Video } from "lucide-react";
import { api } from "../api";
import Layout from "../components/Layout";
import { errorText } from "../lib/copy";
import { MODE_LABEL, fmtDay, fmtTime } from "../lib/format";
import { Alert, Avatar, Button, Card, EmptyState, PageHeader, Segmented, Skeleton, Stamp } from "../ui/kit";

const MODES = [
  { value: "live_audio", label: "Audio", icon: Headphones },
  { value: "live_video", label: "Video", icon: Video },
  { value: "store_forward", label: "Send case", icon: Inbox },
];

function nextDays(n = 10) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    out.push(new Date(d.getFullYear(), d.getMonth(), d.getDate() + i));
  }
  return out;
}

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function BookAppointment() {
  const prefill = useLocation().state || {};
  const days = useMemo(() => nextDays(), []);

  const [patients, setPatients] = useState(null);
  const [search, setSearch] = useState("");
  const [patientId, setPatientId] = useState(prefill.patientId || "");
  const [doctors, setDoctors] = useState(null);
  const [doctorId, setDoctorId] = useState("");
  const [day, setDay] = useState(days[0]);
  const [slots, setSlots] = useState(null);
  const [slot, setSlot] = useState("");
  const [suggested, setSuggested] = useState([]);
  const [mode, setMode] = useState("live_audio");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState(null);

  useEffect(() => {
    api.get("/doctors").then(({ data }) => {
      setDoctors(data);
      if (data.length === 1) setDoctorId(data[0].id);
    });
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      Promise.all([
        api.get("/patients", { params: { search: search || undefined, per_page: 50 } }),
        api.get("/users", { params: { role: "patient", per_page: 100 } }),
      ])
        .then(([{ data: p }, { data: u }]) => {
          const byId = new Map(u.items.map((x) => [x.id, x]));
          setPatients(p.items.map((x) => ({ ...x, name: byId.get(x.user_id)?.name, phone: byId.get(x.user_id)?.phone })));
        })
        .catch((err) => {
          setError(errorText(err, "Could not load patients."));
          setPatients([]);
        });
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    if (!doctorId) return;
    setSlots(null);
    setSlot("");
    api
      .get("/appointments/slots", { params: { doctor_id: doctorId, date: ymd(day) } })
      .then(({ data }) => setSlots(data.available_slots.filter((s) => new Date(s) > Date.now())))
      .catch(() => setSlots([]));
  }, [doctorId, day]);

  const patient = patients?.find((p) => p.id === patientId);
  const doctor = doctors?.find((d) => d.id === doctorId);

  async function book() {
    setError("");
    setBusy(true);
    try {
      const { data } = await api.post("/appointments", {
        patient_id: patientId,
        doctor_id: doctorId,
        scheduled_at: slot,
        consultation_mode: mode,
        notes: notes || undefined,
        idempotency_key: crypto.randomUUID(),
      });
      setBooked(data);
    } catch (err) {
      if (err.response?.status === 409) {
        const alts = err.response.data.alternative_slots || [];
        setSuggested(alts);
        setError("Someone just took that slot. The dashed ones below are free — tap one.");
        if (alts[0]) {
          const d = new Date(alts[0]);
          const match = days.find((x) => x.toDateString() === d.toDateString());
          if (match) setDay(match);
        }
      } else {
        setError(errorText(err, "Could not book the consult."));
      }
    } finally {
      setBusy(false);
    }
  }

  if (booked) {
    return (
      <Layout>
        <PageHeader eyebrow="Booked" title="See you then!" />
        <Card ruled style={{ maxWidth: 560, minHeight: 220 }}>
          <Stamp className="stamp-corner">Booked</Stamp>
          <h3>{patient?.name || "The patient"} with Dr. {doctor?.name?.replace(/^dr\.?\s*/i, "")}</h3>
          <p className="mono" style={{ margin: "0.5rem 0 1.4rem" }}>
            {fmtDay(booked.scheduled_at)} · {fmtTime(booked.scheduled_at)} · {MODE_LABEL[booked.consultation_mode]}
          </p>
          <div className="form-actions">
            <Link className="btn btn-primary" to={`/appointment/${booked.id}`}>
              Open consultation room
            </Link>
            <Button
              variant="secondary"
              onClick={() => {
                setBooked(null);
                setSlot("");
                setPatientId("");
              }}
            >
              Book another
            </Button>
          </div>
        </Card>
      </Layout>
    );
  }

  const daySlots = slots || [];
  const suggestedToday = suggested.filter((s) => new Date(s).toDateString() === day.toDateString() && !daySlots.includes(s));

  return (
    <Layout>
      <PageHeader eyebrow="New consult" title="Book a doctor" />
      <div className="grid-main">
        <div className="stack">
          <Card>
            <div className="card-head">
              <h3>1 · Who is it for?</h3>
              {prefill.patientName && <span className="badge badge-green">Just registered: {prefill.patientName}</span>}
            </div>
            <div className="input-icon" style={{ marginBottom: "0.8rem" }}>
              <Search size={16} />
              <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name…" />
            </div>
            {patients === null ? (
              <Skeleton lines={3} />
            ) : patients.length === 0 ? (
              <EmptyState
                doodle="banyan"
                title="Nobody by that name"
                body="Check the spelling, or register them first."
                action={<Link className="btn btn-secondary" to="/patients/new">Register patient</Link>}
              />
            ) : (
              <div className="picker-list">
                {patients.map((p) => (
                  <button key={p.id} type="button" className={`pick ${p.id === patientId ? "is-selected" : ""}`} onClick={() => setPatientId(p.id)}>
                    <Avatar name={p.name || "?"} size={32} />
                    <span>
                      <strong>{p.name || "Unnamed patient"}</strong>
                      <span className="mono">{p.phone}</span>
                    </span>
                    {p.id === patientId && <Check className="check" size={18} />}
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <h3 style={{ marginBottom: "0.8rem" }}>2 · Which doctor?</h3>
            {doctors === null ? (
              <Skeleton lines={2} />
            ) : doctors.length === 0 ? (
              <EmptyState doodle="lantern" title="No doctors onboarded" body="An admin needs to add one from the Admin desk." />
            ) : (
              <div className="picker-list">
                {doctors.map((d) => (
                  <button key={d.id} type="button" className={`pick ${d.id === doctorId ? "is-selected" : ""}`} onClick={() => setDoctorId(d.id)}>
                    <Avatar name={d.name} size={32} />
                    <span>
                      <strong>Dr. {d.name.replace(/^dr\.?\s*/i, "")}</strong>
                      <span>
                        {d.specialization || "General"} · {d.available_from || "09:00"}–{d.available_to || "17:00"}
                      </span>
                    </span>
                    {d.id === doctorId && <Check className="check" size={18} />}
                  </button>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <h3 style={{ marginBottom: "0.8rem" }}>3 · When?</h3>
            <div className="day-strip">
              {days.map((d) => (
                <button key={d.toISOString()} type="button" className={`day ${d.toDateString() === day.toDateString() ? "is-selected" : ""}`} onClick={() => setDay(d)}>
                  <small>{d.toDateString() === new Date().toDateString() ? "Today" : d.toLocaleDateString(undefined, { weekday: "short" })}</small>
                  <b>{d.getDate()}</b>
                </button>
              ))}
            </div>
            {!doctorId ? (
              <p className="muted">Pick a doctor to see their free slots.</p>
            ) : slots === null ? (
              <Skeleton lines={2} />
            ) : daySlots.length + suggestedToday.length === 0 ? (
              <p className="muted">Fully booked (or past hours) on this day. Try the next one →</p>
            ) : (
              <div className="slots">
                {[...suggestedToday, ...daySlots]
                  .sort()
                  .map((s, i) => (
                    <button
                      key={s}
                      type="button"
                      style={{ "--i": i }}
                      className={`slot ${slot === s ? "is-selected" : ""} ${suggested.includes(s) ? "is-suggested" : ""}`}
                      onClick={() => setSlot(s)}
                    >
                      {fmtTime(s)}
                    </button>
                  ))}
              </div>
            )}
          </Card>
        </div>

        <div className="stack" style={{ position: "sticky", top: "1.5rem" }}>
          <Card>
            <h3 style={{ marginBottom: "0.8rem" }}>How will they talk?</h3>
            <Segmented name="Consultation mode" options={MODES} value={mode} onChange={setMode} />
            <p className="field-hint" style={{ margin: "0.6rem 0 1rem" }}>
              {mode === "live_audio" && "Best on weak signal — about the data of a WhatsApp voice note per minute."}
              {mode === "live_video" && "Needs a decent signal on both ends. Audio can always take over."}
              {mode === "store_forward" && "The doctor answers later from the queue. Good for rashes, reports and photos."}
            </p>
            <textarea
              className="input"
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Note for the doctor (optional)"
              style={{ marginBottom: "1rem" }}
            />
            <div className="summary-ticket">
              <dl>
                <dt>Patient</dt>
                <dd>{patient?.name || "—"}</dd>
                <dt>Doctor</dt>
                <dd>{doctor ? `Dr. ${doctor.name.replace(/^dr\.?\s*/i, "")}` : "—"}</dd>
                <dt>When</dt>
                <dd className="mono">{slot ? `${fmtDay(slot)}, ${fmtTime(slot)}` : "—"}</dd>
              </dl>
            </div>
            <div style={{ marginTop: "1rem" }}>
              <Alert tone={suggested.length ? "orange" : "red"} onClose={() => setError("")}>
                {error}
              </Alert>
              <Button className="btn-block" size="lg" icon={CalendarCheck2} disabled={!patientId || !doctorId || !slot} loading={busy} onClick={book}>
                Book consult
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
