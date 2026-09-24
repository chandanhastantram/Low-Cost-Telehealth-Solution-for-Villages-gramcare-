import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import Layout from "../components/Layout";

function OnboardDoctorForm() {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [specialization, setSpecialization] = useState("");
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      setStatus("Creating account…");
      try {
        await api.post("/auth/otp/request", { phone, name });
      } catch (err) {
        if (err.response?.status !== 400) throw err;
      }
      setStatus("Looking up account…");
      const { data: userList } = await api.get("/users", { params: { phone } });
      const match = userList.items.find((u) => u.phone === phone);
      if (!match) throw new Error("Could not find the account just created.");

      setStatus("Creating doctor profile…");
      await api.post("/doctors", {
        user_id: match.id,
        specialization: specialization || undefined,
        registration_number: registrationNumber || undefined,
      });
      setStatus(`Dr. ${name} onboarded.`);
      setPhone("");
      setName("");
      setSpecialization("");
      setRegistrationNumber("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Could not onboard doctor.");
      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h3>Onboard a doctor</h3>
      <label>Phone number</label>
      <input value={phone} onChange={(e) => setPhone(e.target.value)} required />
      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} required />
      <label>Specialization</label>
      <input value={specialization} onChange={(e) => setSpecialization(e.target.value)} />
      <label>Registration number</label>
      <input value={registrationNumber} onChange={(e) => setRegistrationNumber(e.target.value)} />
      {status && !error && <p className="hint">{status}</p>}
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={loading}>
        {loading ? "Working…" : "Onboard doctor"}
      </button>
    </form>
  );
}

function OnboardCHWForm() {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [qualification, setQualification] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      setStatus("Creating account…");
      try {
        await api.post("/auth/otp/request", { phone, name });
      } catch (err) {
        if (err.response?.status !== 400) throw err;
      }
      setStatus("Looking up account…");
      const { data: userList } = await api.get("/users", { params: { phone } });
      const match = userList.items.find((u) => u.phone === phone);
      if (!match) throw new Error("Could not find the account just created.");

      setStatus("Creating CHW profile…");
      await api.post("/chws", { user_id: match.id, qualification: qualification || undefined });
      setStatus(`${name} onboarded as CHW.`);
      setPhone("");
      setName("");
      setQualification("");
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Could not onboard CHW.");
      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h3>Onboard a community health worker</h3>
      <label>Phone number</label>
      <input value={phone} onChange={(e) => setPhone(e.target.value)} required />
      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} required />
      <label>Qualification</label>
      <input value={qualification} onChange={(e) => setQualification(e.target.value)} />
      {status && !error && <p className="hint">{status}</p>}
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={loading}>
        {loading ? "Working…" : "Onboard CHW"}
      </button>
    </form>
  );
}

function CreateFacilityForm() {
  const [name, setName] = useState("");
  const [district, setDistrict] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/facilities", { name, district, state, pincode });
      setStatus(`Facility "${name}" created.`);
      setName("");
      setDistrict("");
      setState("");
      setPincode("");
    } catch (err) {
      setError(err.response?.data?.detail || "Could not create facility.");
      setStatus("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="form-card" onSubmit={submit}>
      <h3>Create a facility</h3>
      <label>Name</label>
      <input value={name} onChange={(e) => setName(e.target.value)} required />
      <label>District</label>
      <input value={district} onChange={(e) => setDistrict(e.target.value)} />
      <label>State</label>
      <input value={state} onChange={(e) => setState(e.target.value)} />
      <label>Pincode</label>
      <input value={pincode} onChange={(e) => setPincode(e.target.value)} />
      {status && !error && <p className="hint">{status}</p>}
      {error && <p className="error">{error}</p>}
      <button className="button" type="submit" disabled={loading}>
        {loading ? "Working…" : "Create facility"}
      </button>
    </form>
  );
}

function StaffDirectory() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/users", { params: { per_page: 100 } })
      .then(({ data }) => setUsers(data.items || []))
      .catch((err) => setError(err.response?.data?.detail || "Could not load users."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="form-card">
      <h3>Staff &amp; patient directory</h3>
      {loading && <p>Loading…</p>}
      {error && <p className="error">{error}</p>}
      <div className="directory-list">
        {users.map((u) => (
          <div key={u.id} className="directory-row">
            <span>{u.name}</span>
            <span className="meta">{u.phone}</span>
            <span className="role-badge">{u.role}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FacilitiesList() {
  const [facilities, setFacilities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/facilities")
      .then(({ data }) => setFacilities(data))
      .catch((err) => setError(err.response?.data?.detail || "Could not load facilities."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="form-card">
      <h3>Facilities</h3>
      {loading && <p>Loading…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && facilities.length === 0 && <p className="empty">No facilities yet.</p>}
      <div className="directory-list">
        {facilities.map((f) => (
          <div key={f.id} className="directory-row">
            <span>{f.name}</span>
            <span className="meta">
              {f.district}
              {f.district && f.state ? ", " : ""}
              {f.state}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminPanel() {
  return (
    <Layout wide>
      <div className="page page-wide">
        <header className="page-header">
          <h2>Admin panel</h2>
          <Link className="link" to="/audit-log">
            View audit log →
          </Link>
        </header>
        <div className="admin-grid">
          <OnboardDoctorForm />
          <OnboardCHWForm />
          <CreateFacilityForm />
          <StaffDirectory />
          <FacilitiesList />
        </div>
      </div>
    </Layout>
  );
}
