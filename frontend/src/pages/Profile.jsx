import { useEffect, useState } from "react";
import { KeyRound, Moon, ShieldCheck, Sun } from "lucide-react";
import { api, updateStoredUser } from "../api";
import Layout from "../components/Layout";
import { errorText } from "../lib/copy";
import { clearLocalPin, hasLocalPin, saveLocalPin } from "../lib/pin";
import { setTheme, useTheme } from "../theme";
import { Alert, Avatar, Badge, Button, Card, Field, Kbd, PageHeader, Segmented, Skeleton } from "../ui/kit";
import { useToast } from "../ui/toast";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "हिंदी · Hindi" },
  { code: "kn", label: "ಕನ್ನಡ · Kannada" },
  { code: "ta", label: "தமிழ் · Tamil" },
  { code: "te", label: "తెలుగు · Telugu" },
  { code: "mr", label: "मराठी · Marathi" },
  { code: "bn", label: "বাংলা · Bengali" },
];

const ROLE_NAME = { patient: "Patient", chw: "Community health worker", doctor: "Doctor", admin: "Administrator" };

function PinCard({ serverHasPin, onChange }) {
  const toast = useToast();
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = serverHasPin && hasLocalPin();

  async function save(e) {
    e.preventDefault();
    if (pin !== confirm) return setError("The two PINs don't match.");
    setError("");
    setBusy(true);
    try {
      await api.put("/users/me/pin", { pin });
      await saveLocalPin(pin);
      setPin("");
      setConfirm("");
      onChange(true);
      toast("PIN set. Lock the app any time from the sidebar.");
    } catch (err) {
      setError(errorText(err, "Could not set the PIN."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await api.delete("/users/me/pin");
      clearLocalPin();
      onChange(false);
      toast("PIN removed.", "orange");
    } catch (err) {
      setError(errorText(err, "Could not remove the PIN."));
    } finally {
      setBusy(false);
    }
  }

  const digits = (setter) => (e) => setter(e.target.value.replace(/\D/g, "").slice(0, 4));

  return (
    <Card>
      <div className="card-head">
        <h3>
          <KeyRound size={18} /> Offline PIN
        </h3>
        {active ? <Badge tone="green" dot>On</Badge> : <Badge dot>Off</Badge>}
      </div>
      <p className="muted" style={{ marginBottom: "1rem", fontSize: "0.9rem" }}>
        A 4-digit PIN locks GramCare on this phone after 5 idle minutes. It unlocks with no signal at
        all, and five wrong tries log you out — handy if the phone goes missing.
      </p>
      <form onSubmit={save}>
        <div className="form-grid">
          <Field label={active ? "New PIN" : "PIN"}>
            {(id) => <input id={id} type="password" inputMode="numeric" value={pin} onChange={digits(setPin)} pattern="\d{4}" required className="mono" />}
          </Field>
          <Field label="Once more">
            {(id) => <input id={id} type="password" inputMode="numeric" value={confirm} onChange={digits(setConfirm)} pattern="\d{4}" required className="mono" />}
          </Field>
        </div>
        <Alert onClose={() => setError("")}>{error}</Alert>
        <div className="form-actions">
          <Button loading={busy} icon={ShieldCheck}>
            {active ? "Change PIN" : "Turn on PIN"}
          </Button>
          {active && (
            <Button type="button" variant="ghost" onClick={remove} disabled={busy}>
              Remove
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}

export default function Profile() {
  const toast = useToast();
  const { theme } = useTheme();
  const [me, setMe] = useState(null);
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("en");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/users/me")
      .then(({ data }) => {
        setMe(data);
        setName(data.name);
        setLanguage(data.language_code || "en");
      })
      .catch((err) => setError(errorText(err, "Could not load your profile.")));
  }, []);

  async function save(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { data } = await api.patch("/users/me", { name, language_code: language });
      setMe(data);
      updateStoredUser({ name: data.name });
      toast("Saved. Dhanyavaad!");
    } catch (err) {
      setError(errorText(err, "Could not save."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Layout>
      <PageHeader eyebrow="Settings" title="Profile & PIN" />
      <div className="grid-2">
        <Card ruled>
          {!me ? (
            <Skeleton lines={4} />
          ) : (
            <form onSubmit={save}>
              <div style={{ display: "flex", gap: "0.9rem", alignItems: "center", marginBottom: "1.3rem" }}>
                <Avatar name={me.name} size={56} />
                <div>
                  <h2>{me.name}</h2>
                  <span className="muted mono" style={{ fontSize: "0.85rem" }}>
                    {me.phone} · {ROLE_NAME[me.role]}
                  </span>
                </div>
              </div>
              <Field label="Name">{(id) => <input id={id} value={name} onChange={(e) => setName(e.target.value)} required />}</Field>
              <Field label="Language" hint="Prescriptions and reminders are read out in this language.">
                {(id) => (
                  <select id={id} value={language} onChange={(e) => setLanguage(e.target.value)}>
                    {LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.label}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <Alert onClose={() => setError("")}>{error}</Alert>
              <Button loading={busy}>Save changes</Button>
            </form>
          )}
        </Card>

        <div className="stack">
          {me && <PinCard serverHasPin={me.has_offline_pin} onChange={(on) => setMe((m) => ({ ...m, has_offline_pin: on }))} />}

          <Card>
            <h3 style={{ marginBottom: "0.8rem" }}>Appearance</h3>
            <Segmented
              name="Theme"
              value={theme}
              onChange={setTheme}
              options={[
                { value: "light", label: "Daylight", icon: Sun },
                { value: "dark", label: "Lantern", icon: Moon },
              ]}
            />
            <p className="field-hint" style={{ marginTop: "0.6rem" }}>
              Lantern mode is easier on the eyes for night visits — and on the battery.
            </p>
          </Card>

          <Card>
            <h3 style={{ marginBottom: "0.6rem" }}>Shortcuts</h3>
            <p className="muted" style={{ fontSize: "0.9rem", lineHeight: 2 }}>
              <Kbd>Ctrl</Kbd> + <Kbd>K</Kbd> or <Kbd>/</Kbd> quick jump anywhere
              <br />
              Tap the logo five times for something nice.
            </p>
          </Card>
        </div>
      </div>
    </Layout>
  );
}
