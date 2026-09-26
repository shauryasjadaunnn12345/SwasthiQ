import { useEffect, useState } from "react";
import { usePageContext } from "../App.jsx";
import DateSwitcher from "../components/DateSwitcher.jsx";
import { fetchAnalytics, formatRupees } from "../api.js";

function hourLabel(hour) {
  const period = hour < 12 ? "am" : "pm";
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}${period}`;
}

export default function Analytics() {
  const { clinicId, clinicName, days, selectedDate, setSelectedDate } = usePageContext();
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    fetchAnalytics(clinicId, selectedDate)
      .then(setReport)
      .catch((e) => setError(e.message));
  }, [clinicId, selectedDate]);

  if (error) return <div className="banner banner-error">{error}</div>;
  if (!report) return <div className="loading">Loading analytics…</div>;

  const maxRevenue = Math.max(1, ...report.revenue_by_hour.map((h) => h.revenue_paise));

  return (
    <div className="screen">
      <header className="screen-header">
        <div>
          <h1>Analytics</h1>
          <p className="screen-subtitle">{clinicName}</p>
        </div>
        <DateSwitcher days={days} selectedDate={selectedDate} onChange={setSelectedDate} />
      </header>

      <section className="panel">
        <div className="panel-header-row">
          <h2>Revenue by Hour of Day</h2>
          {report.peak_hour && (
            <span className="peak-callout">
              Peak: {hourLabel(report.peak_hour.hour)}–{hourLabel((report.peak_hour.hour + 1) % 24)} —{" "}
              {formatRupees(report.peak_hour.revenue_paise)}
            </span>
          )}
        </div>
        {report.revenue_by_hour.length === 0 ? (
          <p className="empty-note">No sales revenue recorded on this day.</p>
        ) : (
          <div className="bar-chart">
            {report.revenue_by_hour.map((h) => (
              <div className="bar-chart-col" key={h.hour}>
                <div
                  className={"bar" + (report.peak_hour?.hour === h.hour ? " bar-peak" : "")}
                  style={{ height: `${(h.revenue_paise / maxRevenue) * 100}%` }}
                  title={formatRupees(h.revenue_paise)}
                />
                <span className="bar-chart-label">{hourLabel(h.hour)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="two-col">
        <section className="panel">
          <h2>Top Medicines — by Quantity</h2>
          <RankingList
            items={report.top_medicines_by_qty}
            renderValue={(item) => `${item.qty} units`}
          />
        </section>
        <section className="panel">
          <h2>Top Medicines — by Revenue</h2>
          <RankingList
            items={report.top_medicines_by_revenue}
            renderValue={(item) => formatRupees(item.revenue_paise)}
          />
        </section>
      </div>
    </div>
  );
}

function RankingList({ items, renderValue }) {
  if (!items.length) return <p className="empty-note">No medicines moved on this day.</p>;
  return (
    <ol className="ranking-list">
      {items.slice(0, 5).map((item, i) => (
        <li key={item.drug_name}>
          <span className="ranking-index">{i + 1}</span>
          <span className="ranking-name">{item.drug_name}</span>
          <span className="ranking-value">{renderValue(item)}</span>
        </li>
      ))}
    </ol>
  );
}
