import { useState, useEffect, ReactNode } from "react";
import { getHealth } from "../api/client";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * AuthGate checks backend health and the amp_auth cookie.
 * In dev mode, it allows through without auth.
 * In production, it redirects to auth.amphoraxe.ca.
 */
export default function AuthGate({ children }: AuthGateProps) {
  const [checking, setChecking] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [backendError, setBackendError] = useState("");

  useEffect(() => {
    (async () => {
      // Check backend is alive
      try {
        await getHealth();
      } catch {
        setBackendError("Backend unreachable. Is the server running?");
        setChecking(false);
        return;
      }

      // Check if we have the amp_auth cookie
      const hasAuth = document.cookie.split(";").some((c) => c.trim().startsWith("amp_auth="));

      if (hasAuth) {
        setAuthed(true);
      } else if (import.meta.env.DEV) {
        // Allow through in dev mode
        setAuthed(true);
      } else {
        // Redirect to auth service
        window.location.href = `https://auth.amphoraxe.ca/login?redirect=${encodeURIComponent(window.location.href)}`;
        return;
      }
      setChecking(false);
    })();
  }, []);

  if (checking) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <span className="text-muted">Checking authentication...</span>
      </div>
    );
  }

  if (backendError) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh", flexDirection: "column", gap: "1rem" }}>
        <span style={{ color: "var(--error)", fontSize: "1.1rem" }}>{backendError}</span>
        <button className="btn btn-secondary" onClick={() => window.location.reload()}>
          Retry
        </button>
      </div>
    );
  }

  if (!authed) return null;

  return <>{children}</>;
}
