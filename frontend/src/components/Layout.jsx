import { Link, useNavigate } from "react-router-dom";
import { clearSession, getStoredUser } from "../api";

const NAV_BY_ROLE = {
  patient: [{ to: "/dashboard", label: "My appointments" }],
  chw: [
    { to: "/dashboard", label: "Appointments" },
    { to: "/patients/new", label: "Register patient" },
    { to: "/book", label: "Book appointment" },
  ],
  doctor: [
    { to: "/dashboard", label: "Appointments" },
    { to: "/store-forward", label: "Store & forward" },
  ],
  admin: [
    { to: "/dashboard", label: "Appointments" },
    { to: "/patients/new", label: "Register patient" },
    { to: "/book", label: "Book appointment" },
    { to: "/store-forward", label: "Store & forward" },
    { to: "/admin", label: "Admin panel" },
  ],
};

export default function Layout({ children, wide }) {
  const user = getStoredUser();
  const navigate = useNavigate();
  const navItems = NAV_BY_ROLE[user?.role] || [];

  function logout() {
    clearSession();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/dashboard" className="brand">
          GramCare
        </Link>
        <nav className="topnav">
          {navItems.map((item) => (
            <Link key={item.to} to={item.to} className="topnav-link">
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="topbar-user">
          <Link to="/profile" className="topnav-link">
            {user?.name} <span className="role-badge">{user?.role}</span>
          </Link>
          <button className="link" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className={wide ? "app-main app-main-wide" : "app-main"}>{children}</main>
    </div>
  );
}
