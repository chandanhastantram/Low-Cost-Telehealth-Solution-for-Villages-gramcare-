import { useEffect, useState } from "react";
import { api } from "../api";
import Layout from "../components/Layout";

export default function AuditLog() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/audit-logs", { params: { per_page: 100 } })
      .then(({ data }) => setLogs(data.items || []))
      .catch((err) => setError(err.response?.data?.detail || "Could not load audit log."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout wide>
      <div className="page page-wide">
        <header className="page-header">
          <h2>Audit log</h2>
        </header>

        {loading && <p>Loading…</p>}
        {error && <p className="error">{error}</p>}
        {!loading && !error && logs.length === 0 && <p className="empty">No activity recorded yet.</p>}

        <div className="audit-table">
          {logs.map((log) => (
            <div key={log.id} className="audit-row">
              <span className="audit-time">{new Date(log.created_at).toLocaleString()}</span>
              <span className={`audit-action audit-${log.action}`}>{log.action}</span>
              <span className="audit-resource">
                {log.resource_type}
                {log.resource_id ? ` · ${log.resource_id.slice(0, 8)}…` : ""}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
