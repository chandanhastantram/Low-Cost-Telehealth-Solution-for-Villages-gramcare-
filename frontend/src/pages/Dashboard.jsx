import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CalendarCheck2,
  CalendarClock,
  CalendarPlus,
  ChevronRight,
  CircleSlash,
  Inbox,
  Lightbulb,
  Sun,
  UserPlus,
} from "lucide-react";
import { api, getStoredUser } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText, greeting, tipOfTheDay } from "../lib/copy";
import { MODE_LABEL, fmtDay, fmtTime, isToday, relative } from "../lib/format";
import { doctorLabel, patientLabel, usePeople } from "../lib/people";
import { Alert, Card, EmptyState, Loading, Segmented, StatTile, StatusBadge } from "../ui/kit";
import { Toran } from "../ui/doodles";

const ROLE_LINE = {
  patient: "Here's everything booked for you. Your health worker can add more.",
  chw: "Who are we seeing today? Register, take vitals, and get them a doctor.",
  doctor: "Your consultations and any cases waiting in the queue.",
  admin: "The whole register at a glance.",
};

const FILTERS = [
  { value: "upcoming", label: "Upcoming" },
  { value: "all", label: "All" },
  { value: "completed", label: "Done" },
  { value: "cancelled", label: "Cancelled" },
];

function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

function NextUp({ appt, people, isPatient, now }) {
  const d = new Date(appt.scheduled_at);
  return (
    <Card className="next-up" style={{ "--i": 1 }}>
      <div className="calendar-leaf" aria-hidden="true">
        <b>{d.toLocaleString(undefined, { month: "short" })}</b>
        <span>{d.getDate()}</span>
      </div>
      <div>
        <p className="eyebrow">Next up · {fmtTime(d)}</p>
        <h3>{isPatient ? doctorLabel(people, appt.doctor_id) : patientLabel(people, appt.patient_id)}</h3>
        <p className="countdown">
          {MODE_LABEL[appt.consultation_mode]} · {relative(d, now)}
        </p>
      </div>
      <Link className="btn btn-accent" to={`/appointment/${appt.id}`}>
        Open room
      </Link>
    </Card>
  );
}

export default function Dashboard() {
  const user = getStoredUser();
  const people = usePeople();
  const now = useNow();
  const hello = greeting();
  const [appointments, setAppointments] = useState(null);
  const [queueCount, setQueueCount] = useState(null);
  const [filter, setFilter] = useState("upcoming");
  const [error, setError] = useState("");
  const isStaff = user?.role === "chw" || user?.role === "admin";
  const isPatient = user?.role === "patient";

  useEffect(() => {
    api
      .get("/appointments", { params: { per_page: 100 } })
      .then(({ data }) => setAppointments(data.items || []))
      .catch((err) => {
        setError(errorText(err, "Could not load appointments."));
        setAppointments([]);
      });
    if (user?.role === "doctor" || user?.role === "admin") {
      api
        .get("/teleconsult/store-forward", { params: { status_filter: "queued" } })
        .then(({ data }) => setQueueCount(data.length))
        .catch(() => setQueueCount(null));
    }
  }, [user?.role]);

  const stats = useMemo(() => {
    const list = appointments || [];
    const active = list.filter((a) => ["pending", "confirmed"].includes(a.status));
    return {
      today: active.filter((a) => isToday(a.scheduled_at)).length,
      upcoming: active.filter((a) => new Date(a.scheduled_at) > now).length,
      done: list.filter((a) => a.status === "completed").length,
      missed: list.filter((a) => ["cancelled", "no_show"].includes(a.status)).length,
    };
  }, [appointments, now]);

  const next = useMemo(
    () =>
      (appointments || [])
        .filter((a) => ["pending", "confirmed"].includes(a.status) && new Date(a.scheduled_at) > now - 30 * 60000)
        .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))[0],
    [appointments, now]
  );

  const shown = useMemo(() => {
    const list = appointments || [];
    let out;
    if (filter === "upcoming") {
      out = list
        .filter((a) => ["pending", "confirmed"].includes(a.status))
        .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
    } else if (filter === "cancelled") {
      out = list.filter((a) => ["cancelled", "no_show"].includes(a.status));
    } else if (filter === "completed") {
      out = list.filter((a) => a.status === "completed");
    } else {
      out = list;
    }
    return out;
  }, [appointments, filter]);

  const firstName = (user?.name || "").replace(/^dr\.?\s*/i, "").split(" ")[0];

  return (
    <Layout>
      <Toran />
      <div className="hello">
        <div>
          <p className="eyebrow">
            {hello.part} · {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1>
            {hello.word}
            <span className="hello-lang">{hello.lang}</span>, <em>{user?.role === "doctor" ? `Dr. ${firstName}` : firstName}</em>
          </h1>
          <p>{ROLE_LINE[user?.role]}</p>
        </div>
        {isStaff && (
          <div className="page-actions">
            <Link className="btn btn-secondary" to="/patients/new">
              <UserPlus size={17} /> Register
            </Link>
            <Link className="btn btn-primary" to="/book">
              <CalendarPlus size={17} /> Book consult
            </Link>
          </div>
        )}
      </div>

      <div className="stats">
        <StatTile style={{ "--i": 0 }} label="Today" value={appointments ? stats.today : "–"} icon={Sun} tone="orange" note="active consults" />
        <StatTile style={{ "--i": 1 }} label="Upcoming" value={appointments ? stats.upcoming : "–"} icon={CalendarClock} tone="green" note="booked ahead" />
        {queueCount != null ? (
          <StatTile style={{ "--i": 2 }} label="Case queue" value={queueCount} icon={Inbox} tone="red" note="waiting for a doctor" />
        ) : (
          <StatTile style={{ "--i": 2 }} label="Completed" value={appointments ? stats.done : "–"} icon={CalendarCheck2} tone="ink" note="all time" />
        )}
        <StatTile style={{ "--i": 3 }} label="Missed" value={appointments ? stats.missed : "–"} icon={CircleSlash} tone="red" note="cancelled or no-show" />
      </div>

      <div className="grid-main">
        <div className="stack">
          {next && <NextUp appt={next} people={people} isPatient={isPatient} now={now} />}

          <Card style={{ "--i": 2 }}>
            <div className="card-head">
              <h2>The register</h2>
              <Segmented name="Filter appointments" options={FILTERS} value={filter} onChange={setFilter} />
            </div>
            <Alert onClose={() => setError("")}>{error}</Alert>
            {appointments === null ? (
              <Loading />
            ) : shown.length === 0 ? (
              <EmptyState
                {...(isPatient ? EMPTY.appointmentsPatient : EMPTY.appointments)}
                action={
                  isStaff && (
                    <Link className="btn btn-primary" to="/book">
                      Book a consult
                    </Link>
                  )
                }
              />
            ) : (
              <ul className="ledger">
                {shown.map((a, i) => (
                  <li key={a.id}>
                    <Link className="ledger-row" to={`/appointment/${a.id}`} style={{ "--i": i }}>
                      <span className="ledger-no">{String(i + 1).padStart(2, "0")}</span>
                      <span className="ledger-main">
                        <strong>{isPatient ? doctorLabel(people, a.doctor_id) : patientLabel(people, a.patient_id)}</strong>
                        <span>
                          {fmtDay(a.scheduled_at)} · {fmtTime(a.scheduled_at)} · {MODE_LABEL[a.consultation_mode]}
                        </span>
                      </span>
                      <StatusBadge status={a.status} />
                      <ChevronRight className="ledger-arrow" size={18} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <div className="stack">
          {isStaff && (
            <Card style={{ "--i": 3 }}>
              <h3 style={{ marginBottom: "0.9rem" }}>Quick start</h3>
              <div className="quick-actions">
                <Link className="quick-action" to="/patients/new">
                  <span className="qa-icon">
                    <UserPlus size={20} />
                  </span>
                  <span>
                    <strong>New villager</strong>
                    <span>Phone, name, consent — done</span>
                  </span>
                </Link>
                <Link className="quick-action" to="/book">
                  <span className="qa-icon">
                    <CalendarPlus size={20} />
                  </span>
                  <span>
                    <strong>Book a doctor</strong>
                    <span>Pick a free slot in two taps</span>
                  </span>
                </Link>
              </div>
            </Card>
          )}
          {queueCount > 0 && (
            <Card style={{ "--i": 3 }}>
              <h3>{queueCount} case{queueCount === 1 ? "" : "s"} waiting</h3>
              <p className="muted" style={{ margin: "0.3rem 0 0.9rem" }}>
                Sent by health workers when a live call wasn't possible.
              </p>
              <Link className="btn btn-accent" to="/store-forward">
                Open the queue
              </Link>
            </Card>
          )}
          {isPatient && (
            <Card style={{ "--i": 3 }}>
              <h3>Your health file</h3>
              <p className="muted" style={{ margin: "0.3rem 0 0.9rem" }}>
                Every visit, every prescription — readable even on a slow day.
              </p>
              <Link className="btn btn-secondary" to="/my-records">
                Open my records
              </Link>
            </Card>
          )}
          <Card className="tip" style={{ "--i": 4 }}>
            <Lightbulb size={20} />
            <p>
              <b>Tip of the day</b>
              {tipOfTheDay()}
            </p>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
