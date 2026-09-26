const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `Request to ${path} failed (${res.status})`);
  }
  return res.json();
}

export function fetchDays(clinicId) {
  return getJSON(`/clinics/${encodeURIComponent(clinicId)}/days/`);
}

export function fetchReconciliation(clinicId, date) {
  return getJSON(`/clinics/${encodeURIComponent(clinicId)}/days/${date}/reconciliation/`);
}

export function fetchAnalytics(clinicId, date) {
  return getJSON(`/clinics/${encodeURIComponent(clinicId)}/days/${date}/analytics/`);
}

export function fetchNarrative(clinicId, date) {
  return getJSON(`/clinics/${encodeURIComponent(clinicId)}/days/${date}/narrative/`);
}

export async function ingestLog(clinicId, date, rows) {
  const res = await fetch(
    `${API_BASE}/clinics/${encodeURIComponent(clinicId)}/days/${date}/ingest/`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rows),
    }
  );
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Ingest failed");
  return body;
}

export function formatRupees(paise) {
  const value = Math.trunc(paise);
  const sign = value < 0 ? "-" : "";
  const absolutePaise = Math.abs(value);
  const rupees = Math.floor(absolutePaise / 100);
  const paiseRemainder = absolutePaise % 100;
  const amount = rupees.toLocaleString("en-IN");
  return `${sign}₹${amount}${paiseRemainder ? `.${String(paiseRemainder).padStart(2, "0")}` : ""}`;
}

export function formatDateLabel(isoDate) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return d.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}
