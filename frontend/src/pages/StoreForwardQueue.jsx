import { useEffect, useState } from "react";
import { api } from "../api";
import Layout from "../components/Layout";

export default function StoreForwardQueue() {
  const [bundles, setBundles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [responses, setResponses] = useState({});
  const [busyId, setBusyId] = useState(null);

  function load() {
    setLoading(true);
    api
      .get("/teleconsult/store-forward", { params: { status_filter: "queued" } })
      .then(({ data }) => setBundles(data))
      .catch((err) => setError(err.response?.data?.detail || "Could not load queue."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function respond(id) {
    const text = responses[id];
    if (!text?.trim()) return;
    setBusyId(id);
    try {
      await api.post(`/teleconsult/store-forward/${id}/respond`, null, {
        params: { response_text: text },
      });
      setBundles((prev) => prev.filter((b) => b.id !== id));
    } catch (err) {
      setError(err.response?.data?.detail || "Could not send response.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Layout wide>
      <div className="page page-wide">
        <header className="page-header">
          <h2>Store &amp; forward queue</h2>
          <button className="link" onClick={load}>
            Refresh
          </button>
        </header>

        {loading && <p>Loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && bundles.length === 0 && (
          <p className="empty">No pending cases — nice and clear.</p>
        )}

        <div className="sf-list">
          {bundles.map((b) => (
            <div key={b.id} className="sf-card">
              <div className="meta">Submitted {new Date(b.created_at).toLocaleString()}</div>
              <pre className="sf-payload">{JSON.stringify(b.payload_json, null, 2)}</pre>
              <textarea
                placeholder="Write your response / prescription advice…"
                value={responses[b.id] || ""}
                onChange={(e) => setResponses((r) => ({ ...r, [b.id]: e.target.value }))}
                rows={3}
              />
              <button
                className="button"
                onClick={() => respond(b.id)}
                disabled={busyId === b.id}
              >
                {busyId === b.id ? "Sending…" : "Send response"}
              </button>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
