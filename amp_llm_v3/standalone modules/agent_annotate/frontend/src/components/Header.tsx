import { NavLink } from "react-router-dom";

export default function Header() {
  return (
    <header className="header">
      <div className="header-title">{"🕵️"} Agent Annotate</div>
      <nav className="header-nav">
        <NavLink to="/" end className={({ isActive }) => isActive ? "active" : ""}>
          Submit
        </NavLink>
        <NavLink to="/review" className={({ isActive }) => isActive ? "active" : ""}>
          Review
        </NavLink>
        <NavLink to="/results" className={({ isActive }) => isActive ? "active" : ""}>
          Results
        </NavLink>
        <NavLink to="/agreement" className={({ isActive }) => isActive ? "active" : ""}>
          Agreement Metrics
        </NavLink>
        <NavLink to="/jobs" className={({ isActive }) => isActive ? "active" : ""}>
          Jobs
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => isActive ? "active" : ""}>
          Settings
        </NavLink>
      </nav>
    </header>
  );
}
