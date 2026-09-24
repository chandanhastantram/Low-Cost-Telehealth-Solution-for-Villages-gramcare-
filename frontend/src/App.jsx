import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import AppointmentRoom from "./pages/AppointmentRoom";
import RegisterPatient from "./pages/RegisterPatient";
import BookAppointment from "./pages/BookAppointment";
import AdminPanel from "./pages/AdminPanel";
import PatientRecords from "./pages/PatientRecords";
import StoreForwardQueue from "./pages/StoreForwardQueue";
import Profile from "./pages/Profile";
import AuditLog from "./pages/AuditLog";
import NotFound from "./pages/NotFound";
import { getStoredUser } from "./api";

function RequireAuth({ children, roles }) {
  const token = localStorage.getItem("access_token");
  if (!token) return <Navigate to="/login" replace />;
  if (roles) {
    const user = getStoredUser();
    if (!roles.includes(user?.role)) return <Navigate to="/dashboard" replace />;
  }
  return children;
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Dashboard />
            </RequireAuth>
          }
        />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <Profile />
            </RequireAuth>
          }
        />
        <Route
          path="/patients/new"
          element={
            <RequireAuth roles={["chw", "admin"]}>
              <RegisterPatient />
            </RequireAuth>
          }
        />
        <Route
          path="/book"
          element={
            <RequireAuth roles={["chw", "admin"]}>
              <BookAppointment />
            </RequireAuth>
          }
        />
        <Route
          path="/admin"
          element={
            <RequireAuth roles={["admin"]}>
              <AdminPanel />
            </RequireAuth>
          }
        />
        <Route
          path="/audit-log"
          element={
            <RequireAuth roles={["admin"]}>
              <AuditLog />
            </RequireAuth>
          }
        />
        <Route
          path="/appointment/:id"
          element={
            <RequireAuth>
              <AppointmentRoom />
            </RequireAuth>
          }
        />
        <Route
          path="/patients/:id/records"
          element={
            <RequireAuth>
              <PatientRecords />
            </RequireAuth>
          }
        />
        <Route
          path="/store-forward"
          element={
            <RequireAuth roles={["doctor", "admin"]}>
              <StoreForwardQueue />
            </RequireAuth>
          }
        />
        <Route
          path="*"
          element={
            localStorage.getItem("access_token") ? <NotFound /> : <Navigate to="/login" replace />
          }
        />
      </Routes>
    </Router>
  );
}
