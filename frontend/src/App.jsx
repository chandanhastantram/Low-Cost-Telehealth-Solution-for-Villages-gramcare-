import { Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import { getStoredUser } from "./api";
import Shell from "./components/Shell";
import { ToastProvider } from "./ui/toast";
import AdminPanel from "./pages/AdminPanel";
import AppointmentRoom from "./pages/AppointmentRoom";
import AuditLog from "./pages/AuditLog";
import BookAppointment from "./pages/BookAppointment";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import NotFound from "./pages/NotFound";
import PatientRecords from "./pages/PatientRecords";
import Profile from "./pages/Profile";
import RegisterPatient from "./pages/RegisterPatient";
import StoreForwardQueue from "./pages/StoreForwardQueue";

function Only({ roles, children }) {
  return roles.includes(getStoredUser()?.role) ? children : <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <ToastProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route element={<Shell />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/appointment/:id" element={<AppointmentRoom />} />
            <Route path="/patients/:id/records" element={<PatientRecords />} />
            <Route path="/my-records" element={<Only roles={["patient"]}><PatientRecords own /></Only>} />
            <Route path="/patients/new" element={<Only roles={["chw", "admin"]}><RegisterPatient /></Only>} />
            <Route path="/book" element={<Only roles={["chw", "admin"]}><BookAppointment /></Only>} />
            <Route
              path="/store-forward"
              element={<Only roles={["doctor", "chw", "admin"]}><StoreForwardQueue /></Only>}
            />
            <Route path="/admin" element={<Only roles={["admin"]}><AdminPanel /></Only>} />
            <Route path="/audit-log" element={<Only roles={["admin"]}><AuditLog /></Only>} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Router>
    </ToastProvider>
  );
}
