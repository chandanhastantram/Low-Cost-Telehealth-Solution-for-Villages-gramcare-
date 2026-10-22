import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Building2, HeartHandshake, Plus, ScrollText, Search, Stethoscope, Users } from "lucide-react";
import { api } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { invalidatePeople } from "../lib/people";
import { Alert, Avatar, Badge, Button, Card, EmptyState, Field, Loading, PageHeader, Tabs } from "../ui/kit";
import { useToast } from "../ui/toast";

const ROLES = ["patient", "chw", "doctor", "admin"];
const ROLE_TONE = { patient: "neutral", chw: "green", doctor: "orange", admin: "ink" };

/** Find-or-create the user for a phone number (new users get an OTP account). */
async function ensureUser(phone, name) {
  try {
    await api.post("/auth/otp/request", { phone, name });
  } catch (err) {
    if (![400, 429].includes(err.response?.status)) throw err;
  }
  const { data } = await api.get("/users", { params: { phone } });
  const user = data.items.find((u) => u.phone === phone);
  if (!user) throw new Error("Couldn't find or create an account for that number.");
  return user;
}

function People({ facilities }) {
  const toast = useToast();
  const [users, setUsers] = useState(null);
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/users", { params: { per_page: 100, role: roleFilter || undefined } })
      .then(({ data }) => setUsers(data.items))
      .catch((err) => {
        setError(errorText(err, "Could not load people."));
        setUsers([]);
      });
  }, [roleFilter]);

  async function patch(user, change) {
    try {
      const { data } = await api.patch(`/users/${user.id}`, change);
      setUsers((list) => list.map((u) => (u.id === data.id ? data : u)));
      invalidatePeople();
      toast(`${data.name} updated.`);
    } catch (err) {
      toast(errorText(err, "Update failed."), "red");
    }
  }

  const shown = (users || []).filter((u) => `${u.name} ${u.phone}`.toLowerCase().includes(query.toLowerCase()));
  const facilityName = new Map(facilities.map((f) => [f.id, f.name]));

  return (
    <Card>
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div className="input-icon" style={{ flex: "1 1 220px" }}>
          <Search size={16} />
          <input className="input" placeholder="Search name or phone…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <select className="input" style={{ width: "auto" }} value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="">Everyone</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r === "chw" ? "Health workers" : `${r[0].toUpperCase()}${r.slice(1)}s`}
            </option>
          ))}
        </select>
      </div>
      <Alert onClose={() => setError("")}>{error}</Alert>
      {users === null ? (
        <Loading />
      ) : shown.length === 0 ? (
        <EmptyState {...EMPTY.people} />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Person</th>
                <th>Role</th>
                <th>Facility</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((u, i) => (
                <tr key={u.id} style={{ "--i": i }}>
                  <td>
                    <div className="cell-person">
                      <Avatar name={u.name} size={30} />
                      <div>
                        <strong>{u.name}</strong>
                        <div className="mono muted" style={{ fontSize: "0.78rem" }}>
                          {u.phone}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <Badge tone={ROLE_TONE[u.role]}>{u.role === "chw" ? "health worker" : u.role}</Badge>
                  </td>
                  <td>
                    <select
                      value={u.facility_id || ""}
                      onChange={(e) => e.target.value && patch(u, { facility_id: e.target.value })}
                      aria-label={`Facility for ${u.name}`}
                    >
                      <option value="">{u.facility_id ? facilityName.get(u.facility_id) : "— none —"}</option>
                      {facilities
                        .filter((f) => f.id !== u.facility_id)
                        .map((f) => (
                          <option key={f.id} value={f.id}>
                            {f.name}
                          </option>
                        ))}
                    </select>
                  </td>
                  <td>
                    <button
                      className={`badge ${u.is_active ? "badge-green" : "badge-red"}`}
                      style={{ border: "none", cursor: "pointer" }}
                      onClick={() => patch(u, { is_active: !u.is_active })}
                      data-tip={u.is_active ? "Click to deactivate" : "Click to reactivate"}
                    >
                      <i className="badge-dot" /> {u.is_active ? "active" : "inactive"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Facilities({ facilities, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", district: "", state: "", pincode: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { data } = await api.post("/facilities", form);
      onCreated(data);
      setForm({ name: "", district: "", state: "", pincode: "" });
      toast(`${data.name} is on the map.`);
    } catch (err) {
      setError(errorText(err, "Could not create the facility."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-main">
      <Card>
        <h3 style={{ marginBottom: "0.8rem" }}>Facilities</h3>
        {facilities.length === 0 ? (
          <EmptyState doodle="banyan" {...EMPTY.facilities} />
        ) : (
          <ul className="ledger">
            {facilities.map((f, i) => (
              <li key={f.id} className="ledger-row" style={{ "--i": i, gridTemplateColumns: "2.2rem 1fr auto" }}>
                <span className="ledger-no">{String(i + 1).padStart(2, "0")}</span>
                <span className="ledger-main">
                  <strong>{f.name}</strong>
                  <span>{[f.district, f.state].filter(Boolean).join(", ") || "Location not set"}</span>
                </span>
                {f.pincode && <span className="mono muted">{f.pincode}</span>}
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card ruled>
        <h3 style={{ marginBottom: "0.8rem" }}>Add a facility</h3>
        <form onSubmit={create}>
          <Field label="Name">{(id) => <input id={id} value={form.name} onChange={set("name")} placeholder="PHC Hosahalli" required />}</Field>
          <div className="form-grid">
            <Field label="District">{(id) => <input id={id} value={form.district} onChange={set("district")} />}</Field>
            <Field label="State">{(id) => <input id={id} value={form.state} onChange={set("state")} />}</Field>
          </div>
          <Field label="Pincode">{(id) => <input id={id} value={form.pincode} onChange={set("pincode")} inputMode="numeric" pattern="\d{6}" />}</Field>
          <Alert onClose={() => setError("")}>{error}</Alert>
          <Button loading={busy} icon={Plus}>
            Add facility
          </Button>
        </form>
      </Card>
    </div>
  );
}

function Onboard({ kind, facilities }) {
  const toast = useToast();
  const isDoctor = kind === "doctor";
  const [form, setForm] = useState({
    phone: "+91",
    name: "",
    specialization: "",
    registration_number: "",
    available_from: "09:00",
    available_to: "17:00",
    qualification: "",
    facility_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const user = await ensureUser(form.phone, form.name);
      if (isDoctor) {
        await api.post("/doctors", {
          user_id: user.id,
          specialization: form.specialization || undefined,
          registration_number: form.registration_number || undefined,
          available_from: form.available_from,
          available_to: form.available_to,
        });
      } else {
        await api.post("/chws", {
          user_id: user.id,
          qualification: form.qualification || undefined,
          facility_id: form.facility_id || undefined,
        });
      }
      invalidatePeople();
      toast(`${form.name} joined as ${isDoctor ? "a doctor" : "a health worker"}. Swagatam!`);
      setForm((f) => ({ ...f, phone: "+91", name: "", specialization: "", registration_number: "", qualification: "" }));
    } catch (err) {
      setError(errorText(err, "Onboarding failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card ruled>
      <h3 style={{ marginBottom: "0.8rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
        {isDoctor ? <Stethoscope size={18} /> : <HeartHandshake size={18} />}
        {isDoctor ? "Onboard a doctor" : "Onboard a health worker"}
      </h3>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Mobile number">{(id) => <input id={id} value={form.phone} onChange={set("phone")} inputMode="tel" required />}</Field>
          <Field label="Name">{(id) => <input id={id} value={form.name} onChange={set("name")} required />}</Field>
          {isDoctor ? (
            <>
              <Field label="Specialisation">{(id) => <input id={id} value={form.specialization} onChange={set("specialization")} placeholder="General medicine" />}</Field>
              <Field label="Registration no.">{(id) => <input id={id} value={form.registration_number} onChange={set("registration_number")} />}</Field>
              <Field label="Available from">{(id) => <input id={id} type="time" value={form.available_from} onChange={set("available_from")} />}</Field>
              <Field label="Available until">{(id) => <input id={id} type="time" value={form.available_to} onChange={set("available_to")} />}</Field>
            </>
          ) : (
            <>
              <Field label="Qualification">{(id) => <input id={id} value={form.qualification} onChange={set("qualification")} placeholder="ASHA, ANM…" />}</Field>
              <Field label="Facility" hint="They'll only see patients registered here">
                {(id) => (
                  <select id={id} value={form.facility_id} onChange={set("facility_id")} required>
                    <option value="">Choose…</option>
                    {facilities.map((f) => (
                      <option key={f.id} value={f.id}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </>
          )}
        </div>
        <Alert onClose={() => setError("")}>{error}</Alert>
        <Button loading={busy}>{isDoctor ? "Onboard doctor" : "Onboard health worker"}</Button>
      </form>
    </Card>
  );
}

export default function AdminPanel() {
  const [tab, setTab] = useState("people");
  const [facilities, setFacilities] = useState([]);

  useEffect(() => {
    api.get("/facilities").then(({ data }) => setFacilities(data));
  }, []);

  return (
    <Layout>
      <PageHeader eyebrow="Administration" title="Admin desk">
        <Link className="btn btn-secondary" to="/audit-log">
          <ScrollText size={17} /> Audit trail
        </Link>
      </PageHeader>
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "people", label: "People", icon: Users },
          { value: "facilities", label: "Facilities", icon: Building2, count: facilities.length },
          { value: "onboard", label: "Onboard staff", icon: Plus },
        ]}
      />
      {tab === "people" && <People facilities={facilities} />}
      {tab === "facilities" && <Facilities facilities={facilities} onCreated={(f) => setFacilities((list) => [...list, f])} />}
      {tab === "onboard" && (
        <div className="grid-2">
          <Onboard kind="doctor" facilities={facilities} />
          <Onboard kind="chw" facilities={facilities} />
        </div>
      )}
    </Layout>
  );
}
