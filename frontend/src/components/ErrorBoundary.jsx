import { Component } from "react";

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("GramCare UI crashed:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="auth-screen">
          <div className="auth-card">
            <h1>Something went wrong</h1>
            <p className="subtitle">{this.state.error.message || "Unexpected error."}</p>
            <button className="button" onClick={() => window.location.assign("/dashboard")}>
              Back to dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
