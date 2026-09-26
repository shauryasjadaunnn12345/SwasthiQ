import { useEffect, useState } from "react";
import { usePageContext } from "../App.jsx";
import DateSwitcher from "../components/DateSwitcher.jsx";
import { fetchReconciliation, formatDateLabel, formatRupees } from "../api.js";

export default function Reconciliation() {
  const { clinicId, clinicName, clinicLocation, days, selectedDate, setSelectedDate } =
    usePageContext();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    fetchReconciliation(clinicId, selectedDate)
      .then(setReport)
      .catch((e) => setError(e.message));
  }, [clinicId, selectedDate]);

  if (error) return <div className="banner banner-error">{error}</div>;
  if (!report) return <div className="loading">Loading reconciliation…</div>;

  const modeRows = Object.entries(report.by_payment_mode);

  return (
    <div className="screen">
      <header className="screen-header">
        <div>
          <h1>EOD Reconciliation</h1>
          <p className="screen-subtitle">
            {clinicName} — {clinicLocation}
          </p>
        </div>
        <DateSwitcher days={days} selectedDate={selectedDate} onChange={setSelectedDate} />
      </header>

      <div className="stat-cards">
        <StatCard
          label="Total Billed"
          value={formatRupees(report.total_billed_paise)}
          sub={`${report.visit_count} visits`}
        />
        <StatCard
          label="Total Collected"
          value={formatRupees(report.total_collected_paise)}
          sub={
            report.collected_pct_of_billed !== null
              ? `${report.collected_pct_of_billed}% of billed`
              : "—"
          }
        />
        <StatCard
          label="Outstanding"
          value={formatRupees(report.total_outstanding_paise)}
          sub={`${report.outstanding_visit_count} pending visit${report.outstanding_visit_count === 1 ? "" : "s"}`}
          tone={report.total_outstanding_paise > 0 ? "warn" : "default"}
        />
        <StatCard
          label="Refunds"
          value={formatRupees(report.total_refunds_paise)}
          sub={`${report.refund_count} refund${report.refund_count === 1 ? "" : "s"}`}
          tone={report.total_refunds_paise > 0 ? "danger" : "default"}
        />
      </div>

      <section className="panel">
        <h2>Payment Mode Breakdown</h2>
        <table className="data-table">
          <thead>
            <tr>
              <th>Mode</th>
              <th>Billed</th>
              <th>Collected</th>
              <th>Outstanding</th>
              <th>Refunds</th>
            </tr>
          </thead>
          <tbody>
            {modeRows.map(([mode, figures]) => (
              <tr key={mode}>
                <td className="capitalize">{mode}</td>
                <td>{formatRupees(figures.billed_paise)}</td>
                <td>{formatRupees(figures.collected_paise)}</td>
                <td>{formatRupees(figures.outstanding_paise)}</td>
                <td>{formatRupees(figures.refunds_paise)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function StatCard({ label, value, sub, tone = "default" }) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <div className="stat-card-label">{label.toUpperCase()}</div>
      <div className="stat-card-value">{value}</div>
      <div className="stat-card-sub">{sub}</div>
    </div>
  );
}
