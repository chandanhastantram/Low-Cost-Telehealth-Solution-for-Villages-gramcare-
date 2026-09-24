import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getStoredUser } from "../api";
import Layout from "../components/Layout";

const ROLE_COPY = {
  patient: {
    title: "Your care",
    blurb: "Your appointments, consultations and records — all in one place.",
  },
  chw: {
    title: "Community health worker",
    blurb: "Register patients, book appointments, and run consultations on their behalf.",
  },
  doctor: {
    title: "Doctor queue",
    blurb: "Your upcoming and pending consultations.",
  },
  admin: {
    title: "Administration",
    blurb: "Onboard staff, manage facilities, and audit platform activity.",
  },
};

const STATUS_FILTERS = ["all", "pending", "confirmed", "completed", "cancelled"];

export default function Dashboard() {
  const user = getStoredUser();
  const [appointments, setAppointments] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get("/appointments", {
        params: statusFilter === "all" ? {} : { status: statusFilter },
      })
      .then(({ data }) => {
        if (!cancelled) setAppointments(data.items || []);
      })
      .catch((err) => {
        if (!cancelled) setError(err.response?.data?.detail || "Could not load appointments.");
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [statusFilter]);

  const copy = ROLE_COPY[user?.role] || ROLE_COPY.patient;

  return (
    <Layout>
      <div className="dashboard">
        <section className="role-intro">
          <h2>{copy.title}</h2>
          <p className="subtitle">{copy.blurb}</p>

          <div className="action-row">
            {(user?.role === "chw" || user?.role === "admin") && (
              <>
                <Link className="button" to="/patients/new">
                  + Register patient
                </Link>
                <Link className="button secondary" to="/book">
                  + Book appointment
                </Link>
              </>
            )}
          </div>
        </section>

        <section>
          <div className="section-header">
            <h2>Appointments</h2>
            <div className="filter-row">
              {STATUS_FILTERS.map((s) => (
                <button
                  key={s}
                  className={`filter-chip ${statusFilter === s ? "active" : ""}`}
                  onClick={() => setStatusFilter(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {loading && <p>Loading…</p>}
          {error && <p className="error">{error}</p>}
          {!loading && !error && appointments.length === 0 && (
            <p className="empty">
              No {statusFilter === "all" ? "" : statusFilter} appointments.
              {(user?.role === "chw" || user?.role === "admin") && (
                <>
                  {" "}
                  <Link className="link" to="/book">
                    Book one now
                  </Link>
                  .
                </>
              )}
            </p>
          )}
          <ul className="appointment-list">
            {appointments.map((appt) => (
              <li key={appt.id} className="appointment-card">
                <div>
                  <strong>{new Date(appt.scheduled_at).toLocaleString()}</strong>
                  <div className="meta">
                    {appt.consultation_mode.replace("_", " ")} · {appt.status}
                  </div>
                </div>
                <Link className="button" to={`/appointment/${appt.id}`}>
                  Open
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </Layout>
  );
}
