import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/reconciliation", label: "EOD Reconciliation", icon: "🧾" },
  { to: "/analytics", label: "Analytics", icon: "📊" },
  { to: "/narrative", label: "AI Narrative Summary", icon: "💬" },
];

export default function Sidebar({ clinicName, clinicLocation }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">SQ</div>
        <div>
          <div className="sidebar-brand-name">SwasthiQ</div>
          <div className="sidebar-brand-sub">Kaagazy</div>
        </div>
      </div>

      <div className="sidebar-clinic">
        <div className="sidebar-clinic-name">{clinicName}</div>
        <div className="sidebar-clinic-location">{clinicLocation}</div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => "sidebar-nav-item" + (isActive ? " active" : "")}
          >
            <span className="sidebar-nav-icon" aria-hidden="true">
              {item.icon}
            </span>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
