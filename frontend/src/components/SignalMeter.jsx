import { useEffect, useState } from "react";
import { API_URL } from "../api";
import { SignalBars } from "../ui/doodles";

// Measures round-trip time to /health and shows it the way people in the
// field actually talk about connectivity.
function describe(ms) {
  if (ms == null) return { level: 0, text: "Offline", tip: "No signal — work is kept on this device", cls: "is-offline" };
  if (ms < 300) return { level: 4, text: "Good signal", tip: `${ms} ms · smooth as fresh roads`, cls: "" };
  if (ms < 900) return { level: 3, text: "Okay signal", tip: `${ms} ms · calls should work`, cls: "" };
  if (ms < 2000) return { level: 2, text: "2G mood", tip: `${ms} ms · audio only, please`, cls: "is-weak" };
  return { level: 1, text: "Barely there", tip: `${ms} ms · try store-and-forward`, cls: "is-weak" };
}

export default function SignalMeter() {
  const [latency, setLatency] = useState(undefined);

  useEffect(() => {
    let alive = true;
    async function ping() {
      if (!navigator.onLine) return alive && setLatency(null);
      const started = performance.now();
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 6000);
        const res = await fetch(`${API_URL}/health`, { cache: "no-store", signal: ctrl.signal });
        clearTimeout(timer);
        if (alive) setLatency(res.ok ? Math.round(performance.now() - started) : null);
      } catch {
        if (alive) setLatency(null);
      }
    }
    ping();
    const t = setInterval(ping, 30_000);
    window.addEventListener("online", ping);
    window.addEventListener("offline", ping);
    return () => {
      alive = false;
      clearInterval(t);
      window.removeEventListener("online", ping);
      window.removeEventListener("offline", ping);
    };
  }, []);

  if (latency === undefined) {
    return (
      <span className="signal">
        <SignalBars level={0} />
        <span className="signal-text">Checking…</span>
      </span>
    );
  }
  const d = describe(latency);
  return (
    <span className={`signal ${d.cls}`} data-tip={d.tip}>
      <SignalBars level={d.level} key={d.level} />
      <span className="signal-text">{d.text}</span>
    </span>
  );
}
