import { useState, useEffect, ReactNode } from "react";

interface AuthGateProps {
  children: ReactNode;
}

/**
 * AuthGate checks for the amp_auth cookie.
 * In dev mode, it allows through without auth.
 * In production, it redirects to auth.amphoraxe.ca.
 */
export default function AuthGate({ children }: AuthGateProps) {
  const [checking, setChecking] = useState(true);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
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
  }, []);

  if (checking) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <span className="text-muted">Checking authentication...</span>
      </div>
    );
  }

  if (!authed) return null;

  return <>{children}</>;
}
