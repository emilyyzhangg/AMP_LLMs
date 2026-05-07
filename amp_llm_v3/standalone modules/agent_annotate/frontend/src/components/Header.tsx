import { NavLink, useLocation } from "react-router-dom";
import type { MouseEvent } from "react";

export default function Header() {
  const location = useLocation();

  // Clicking a nav item that's already active re-runs the page's mount-time
  // data fetch via a hard reload. React Router otherwise no-ops the click
  // because the URL didn't change.
  function reloadIfActive(to: string, end = false) {
    return (e: MouseEvent<HTMLAnchorElement>) => {
      const isActive = end
        ? location.pathname === to
        : location.pathname === to || location.pathname.startsWith(to + "/");
      if (isActive) {
        e.preventDefault();
        window.location.reload();
      }
    };
  }

  return (
    <header className="header">
      <div className="header-title">{"🕵️"} Agent Annotate</div>
      <nav className="header-nav">
        <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/", true)}>
          Submit
        </NavLink>
        <NavLink to="/review" className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/review")}>
          Review
        </NavLink>
        <NavLink to="/results" className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/results")}>
          Results
        </NavLink>
        <NavLink to="/agreement" className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/agreement")}>
          Agreement Metrics
        </NavLink>
        <NavLink to="/jobs" className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/jobs")}>
          Jobs
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => isActive ? "active" : ""} onClick={reloadIfActive("/settings")}>
          Settings
        </NavLink>
      </nav>
    </header>
  );
}
