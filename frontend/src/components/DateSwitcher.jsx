import { formatDateLabel } from "../api.js";

export default function DateSwitcher({ days, selectedDate, onChange }) {
  if (!days.length) return null;
  return (
    <label className="date-switcher">
      <span aria-hidden="true">📅</span>
      <select value={selectedDate} onChange={(e) => onChange(e.target.value)}>
        {days.map((d) => (
          <option key={d.date} value={d.date}>
            {formatDateLabel(d.date)}
          </option>
        ))}
      </select>
    </label>
  );
}
