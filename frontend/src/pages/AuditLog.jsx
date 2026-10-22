import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api } from "../api";
import Layout from "../components/Layout";
import { EMPTY, errorText } from "../lib/copy";
import { fmtFull, relative } from "../lib/format";
import { Alert, Badge, Button, Card, EmptyState, Loading, PageHeader, Segmented } from "../ui/kit";

const PER_PAGE = 50;
const ACTION_TONE = { create: "green", update: "orange", delete: "red", read: "neutral", login: "ink", logout: "ink", sync: "neutral" };
const FILTERS = [
  { value: "", label: "All" },
  { value: "patient_profile", label: "Patients" },
  { value: "encounter", label: "Visits" },
  { value: "prescription", label: "Prescriptions" },
  { value: "appointment", label: "Appointments" },
  { value: "user", label: "Users" },
];

export default function AuditLog() {
  const [page, setPage] = useState(1);
  const [resource, setResource] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setData(null);
    api
      .get("/audit-logs", { params: { page, per_page: PER_PAGE, resource_type: resource || undefined } })
      .then(({ data }) => setData(data))
      .catch((err) => {
        setError(errorText(err, "Could not load the audit trail."));
        setData({ items: [], total: 0 });
      });
  }, [page, resource]);

  const pages = data ? Math.max(1, Math.ceil(data.total / PER_PAGE)) : 1;

  return (
    <Layout>
      <PageHeader eyebrow="Append-only" title="Audit trail" />
      <Card>
        <div className="card-head" style={{ flexWrap: "wrap" }}>
          <Segmented
            name="Filter"
            options={FILTERS}
            value={resource}
            onChange={(v) => {
              setResource(v);
              setPage(1);
            }}
          />
          {data && <span className="muted mono">{data.total} entries</span>}
        </div>
        <Alert onClose={() => setError("")}>{error}</Alert>
        {data === null ? (
          <Loading lines={6} />
        ) : data.items.length === 0 ? (
          <EmptyState doodle="lantern" {...EMPTY.audit} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Action</th>
                  <th>What</th>
                  <th>Who</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((log, i) => (
                  <tr key={log.id} style={{ "--i": i }}>
                    <td data-tip={fmtFull(log.created_at)} style={{ position: "relative", whiteSpace: "nowrap" }}>
                      {relative(log.created_at)}
                    </td>
                    <td>
                      <Badge tone={ACTION_TONE[log.action]}>{log.action}</Badge>
                    </td>
                    <td>
                      {log.resource_type?.replaceAll("_", " ")}
                      {log.resource_id && <span className="mono muted"> · {log.resource_id.slice(0, 8)}</span>}
                    </td>
                    <td className="mono muted">{log.actor_id ? log.actor_id.slice(0, 8) : "system"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="form-actions" style={{ justifyContent: "flex-end", marginTop: "1rem" }}>
            <Button variant="secondary" size="sm" icon={ChevronLeft} disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
              Newer
            </Button>
            <span className="mono muted">
              {page} / {pages}
            </span>
            <Button variant="secondary" size="sm" icon={ChevronRight} disabled={page === pages} onClick={() => setPage((p) => p + 1)}>
              Older
            </Button>
          </div>
        )}
      </Card>
    </Layout>
  );
}
