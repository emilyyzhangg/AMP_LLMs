import { useState, useEffect, ReactNode } from "react";
import { getHealth } from "../api/client";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * AuthGate verifies the backend is reachable.
 * Authentication is handled at the Cloudflare Access layer —
 * if the user reached this page, they're already authenticated.
 */
export default function AuthGate({ children }: AuthGateProps) {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        await getHealth();
        setReady(true);
      } catch {
        setError("Backend unreachable. Is the server running?");
      }
    })();
  }, []);

  if (error) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", flexDirection: "column", gap: "1rem" }}>
        <span style={{ color: "var(--error)", fontSize: "1.1rem" }}>{error}</span>
        <button className="btn btn-secondary" onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  if (!ready) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <span className="text-muted">Loading Agent Annotate...</span>
      </div>
    );
  }

  return <>{children}</>;
}
