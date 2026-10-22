import { useEffect, useState } from "react";
import { api, getStoredUser } from "../api";

// Appointments and records only carry ids. Staff can resolve them to names
// via the patient + user + doctor directories; patients can't (and don't
// need to), so for them this stays empty and the UI falls back gracefully.
let cache = null;

async function load() {
  const role = getStoredUser()?.role;
  if (!["chw", "doctor", "admin"].includes(role)) return { patients: new Map(), doctors: new Map() };
  const [patients, users, doctors] = await Promise.all([
    api.get("/patients", { params: { per_page: 100 } }).then((r) => r.data.items || []),
    api.get("/users", { params: { role: "patient", per_page: 100 } }).then((r) => r.data.items || []),
    api.get("/doctors").then((r) => r.data || []),
  ]);
  const usersById = new Map(users.map((u) => [u.id, u]));
  return {
    patients: new Map(
      patients.map((p) => [p.id, { ...p, name: usersById.get(p.user_id)?.name, phone: usersById.get(p.user_id)?.phone }])
    ),
    doctors: new Map(doctors.map((d) => [d.id, d])),
  };
}

export function invalidatePeople() {
  cache = null;
}

export function usePeople() {
  const [people, setPeople] = useState({ patients: new Map(), doctors: new Map(), ready: false });
  useEffect(() => {
    let alive = true;
    if (!cache) cache = load().catch(() => ({ patients: new Map(), doctors: new Map() }));
    cache.then((p) => alive && setPeople({ ...p, ready: true }));
    return () => {
      alive = false;
    };
  }, []);
  return people;
}

export function patientLabel(people, id) {
  const p = people.patients.get(id);
  return p?.name || `Patient #${String(id).slice(0, 6)}`;
}

export function doctorLabel(people, id) {
  const d = people.doctors.get(id);
  return d ? `Dr. ${d.name.replace(/^dr\.?\s*/i, "")}` : "Assigned doctor";
}
