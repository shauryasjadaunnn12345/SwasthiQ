import { useEffect, useState } from "react";
import { Navigate, Outlet, Route, Routes, useOutletContext } from "react-router-dom";
import Sidebar from "./components/Sidebar.jsx";
import { fetchDays } from "./api.js";
import Reconciliation from "./pages/Reconciliation.jsx";
import Analytics from "./pages/Analytics.jsx";
import Narrative from "./pages/Narrative.jsx";

const CLINIC_ID = import.meta.env.VITE_CLINIC_ID || "CLN-KNP-014";
const CLINIC_NAME = import.meta.env.VITE_CLINIC_NAME || "Mehta Multi-Specialty Clinic";
const CLINIC_LOCATION = import.meta.env.VITE_CLINIC_LOCATION || "Kanpur, Uttar Pradesh";

function Layout() {
  const [days, setDays] = useState([]);
  const [selectedDate, setSelectedDate] = useState(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    fetchDays(CLINIC_ID)
      .then((result) => {
        setDays(result);
        if (result.length) setSelectedDate(result[0].date);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  return (
    <div className="app-shell">
      <Sidebar clinicName={CLINIC_NAME} clinicLocation={CLINIC_LOCATION} />
      <main className="app-main">
        {loadError && (
          <div className="banner banner-error">
            Couldn't reach the API: {loadError}. Is the Django backend running on
            port 8000?
          </div>
        )}
        {!loadError && days.length === 0 && (
          <div className="banner">
            No billing days ingested yet for {CLINIC_ID}. POST a log to{" "}
            <code>/api/clinics/{CLINIC_ID}/days/&lt;date&gt;/ingest/</code> to get started.
          </div>
        )}
        {selectedDate && (
          <Outlet
            context={{
              clinicId: CLINIC_ID,
              clinicName: CLINIC_NAME,
              clinicLocation: CLINIC_LOCATION,
              days,
              selectedDate,
              setSelectedDate,
            }}
          />
        )}
      </main>
    </div>
  );
}

export function usePageContext() {
  return useOutletContext();
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/reconciliation" replace />} />
        <Route path="reconciliation" element={<Reconciliation />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="narrative" element={<Narrative />} />
      </Route>
    </Routes>
  );
}
