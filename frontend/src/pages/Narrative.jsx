import { useEffect, useState } from "react";
import { usePageContext } from "../App.jsx";
import DateSwitcher from "../components/DateSwitcher.jsx";
import { fetchNarrative, formatDateLabel } from "../api.js";

export default function Narrative() {
  const { clinicId, clinicName, days, selectedDate, setSelectedDate } = usePageContext();
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    setError(null);
    fetchNarrative(clinicId, selectedDate)
      .then(setResult)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [clinicId, selectedDate]);

  if (error) return <div className="banner banner-error">{error}</div>;

  return (
    <div className="screen">
      <header className="screen-header">
        <div>
          <h1>AI Narrative Summary</h1>
          <p className="screen-subtitle">
            Generated from today's reconciliation — {clinicName}
          </p>
        </div>
        <DateSwitcher days={days} selectedDate={selectedDate} onChange={setSelectedDate} />
      </header>

      {loading || !result ? (
        <div className="loading">Generating summary…</div>
      ) : (
        <>
          {result.source === "fallback_template" && (
            <div className="banner banner-warn">
              AI narrative is temporarily unavailable. This verified template
              summary uses the deterministic report.
            </div>
          )}
          <div className="two-col narrative-layout">
            <section className="panel narrative-panel">
              <div className="narrative-panel-tag">
                {result.source === "llm" ? "AI SUGGESTED" : "TEMPLATE FALLBACK"}
              </div>
              <div className="whatsapp-bubble">
                <div className="whatsapp-bubble-meta">
                  Sent to clinic owner · WhatsApp · {formatDateLabel(selectedDate)}
                </div>
                {result.narrative.split("\n").map((line, i) => (
                  <p key={i}>{line}</p>
                ))}
              </div>
            </section>

            <section className="panel traced-panel">
              <h2>Traced Figures</h2>
              <p className="traced-panel-note">
                Every number above maps to the deterministic report — this is what
                gets auto-checked.
              </p>
              <ul className="traced-list">
                {result.traced_figures.map((tf, i) => (
                  <li key={i}>
                    <span className="traced-value">{tf.text}</span>
                    <span className="traced-field">{tf.field}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
          <button className="regenerate-btn" onClick={load}>
            Regenerate
          </button>
        </>
      )}
    </div>
  );
}
