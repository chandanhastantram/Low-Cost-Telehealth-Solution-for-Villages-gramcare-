import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="auth-screen">
      <div className="auth-card" style={{ textAlign: "center" }}>
        <h1>404</h1>
        <p className="subtitle">That page doesn't exist.</p>
        <Link className="button" to="/dashboard">
          Back to dashboard
        </Link>
      </div>
    </div>
  );
}
