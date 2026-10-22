import { Component } from "react";
import { Lantern } from "../ui/doodles";
import ThemeToggle from "./ThemeToggle";

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("GramCare UI crashed:", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="lost">
        <div className="theme-float">
          <ThemeToggle />
        </div>
        <div>
          <Lantern size={80} />
          <h1 style={{ marginTop: "1rem" }}>The lamp flickered out</h1>
          <p>
            Something on this page broke. Nothing you entered has been sent twice — it's safe to
            go back and try again.
          </p>
          <p className="mono" style={{ fontSize: "0.8rem" }}>{this.state.error.message}</p>
          <button className="btn btn-primary" onClick={() => window.location.assign("/dashboard")}>
            Back to today's register
          </button>
        </div>
      </div>
    );
  }
}
