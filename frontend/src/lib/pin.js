// Offline unlock PIN. The device keeps a salted SHA-256 of the PIN so the app
// can be unlocked with no network; the server keeps its own bcrypt copy
// (PUT /users/me/pin) for re-verification on a new device.

const KEY = "gc-pin";

async function digest(salt, pin) {
  const bytes = new TextEncoder().encode(`${salt}:${pin}`);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function hasLocalPin() {
  try {
    return Boolean(localStorage.getItem(KEY));
  } catch {
    return false;
  }
}

export async function saveLocalPin(pin) {
  const salt = crypto.randomUUID();
  localStorage.setItem(KEY, JSON.stringify({ salt, hash: await digest(salt, pin), fails: 0 }));
}

export function clearLocalPin() {
  localStorage.removeItem(KEY);
}

/** Returns { ok, remaining }. After 5 wrong tries the caller should log out. */
export async function checkLocalPin(pin) {
  const stored = JSON.parse(localStorage.getItem(KEY) || "null");
  if (!stored) return { ok: true, remaining: 5 };
  const ok = (await digest(stored.salt, pin)) === stored.hash;
  stored.fails = ok ? 0 : (stored.fails || 0) + 1;
  localStorage.setItem(KEY, JSON.stringify(stored));
  return { ok, remaining: Math.max(5 - stored.fails, 0) };
}
