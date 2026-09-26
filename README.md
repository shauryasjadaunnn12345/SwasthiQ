# SwasthiQ — EOD Billing & Analytics Agent

A Python REST API (Django) that turns a clinic's raw daily billing log into
a deterministic end-of-day reconciliation, deterministic analytics, and a
grounded LLM narrative summary — plus a React frontend for the three screens
in the brief.

```
/backend    Django REST API
/frontend   React (Vite) app — sidebar + 3 screens
/sample_data  The provided 3-day sample dataset, used by the backend tests
```

## Quick start

### Backend

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver          # http://localhost:8000
```

On Windows, use PowerShell:

```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

To enable the AI narrative, copy `.env.example` to `.env`, fill in
`MISTRAL_API_KEY` (free tier at https://console.mistral.ai/), and export it
(e.g. `export $(cat .env | xargs)`) before running the server — `manage.py`
does not auto-load `.env`. Without a key, the narrative endpoint still
works: it returns a template-generated summary instead of calling Mistral
(see "Narrative layer" below).

In PowerShell, set the key in the same terminal before starting the server:

```powershell
$env:MISTRAL_API_KEY = "your-key"
```

### Use PostgreSQL on Render

To use Render's managed PostgreSQL database, create a database in the same
Render region as the backend web service. In the web service's Environment
settings, add `DATABASE_URL` using the database's **Internal Database URL**.
The backend selects PostgreSQL when `DATABASE_URL` is set; otherwise it uses
SQLite locally.

Set the web service start command to run migrations before Gunicorn starts:

```text
python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

After the first deployment, ingest the sample logs again because a new
PostgreSQL database starts empty. PostgreSQL is outside the assignment's
stated SQLite/in-memory storage constraint, so use it only if the evaluator
allows this deployment change.

### Persist SQLite data on Render

Render's service filesystem is ephemeral unless a persistent disk is attached.
Persistent disks are available for paid web services and support one service
instance. To keep the SQLite database across restarts and deploys:

1. Open the backend web service in Render and add a persistent disk with mount
  path `/var/data`.
2. Add the environment variable `DJANGO_SQLITE_PATH` with value
  `/var/data/db.sqlite3`.
3. Save the disk and environment settings, then wait for the service to redeploy.
4. Re-ingest the sample logs if needed. A newly attached disk starts empty; it
  does not copy a database from the old ephemeral filesystem.

Locally, if `DJANGO_SQLITE_PATH` is unset, SQLite continues to use
`backend/db.sqlite3`.

Run the test suite (41 tests — validation, ingestion, reconciliation,
analytics, narrative grounding, and the HTTP endpoints):

```bash
python manage.py test billing
```

### Ingest the sample data

```bash
curl -X POST http://localhost:8000/api/clinics/CLN-KNP-014/days/2026-07-27/ingest/ \
  -H "Content-Type: application/json" \
  --data @../sample_data/billing_log_2026-07-27.json

curl -X POST http://localhost:8000/api/clinics/CLN-KNP-014/days/2026-07-26/ingest/ \
  -H "Content-Type: application/json" --data @../sample_data/billing_log_2026-07-26.json

curl -X POST http://localhost:8000/api/clinics/CLN-KNP-014/days/2026-07-25/ingest/ \
  -H "Content-Type: application/json" --data @../sample_data/billing_log_2026-07-25.json
```

In Windows PowerShell, `Invoke-RestMethod` can upload a sample file directly:

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/clinics/CLN-KNP-014/days/2026-07-27/ingest/" -ContentType "application/json" -InFile "..\sample_data\billing_log_2026-07-27.json"
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

`.env.example` → `.env` lets you point `VITE_API_BASE_URL` at a deployed
backend and set which `VITE_CLINIC_ID` the UI displays.

## API contract

All amounts are integer paise. All endpoints return JSON.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/clinics/<clinic_id>/days/<YYYY-MM-DD>/ingest/` | Ingest (or re-ingest) one day's billing log |
| `GET` | `/api/clinics/<clinic_id>/days/` | List days ingested for this clinic |
| `GET` | `/api/clinics/<clinic_id>/days/<YYYY-MM-DD>/reconciliation/` | Deterministic EOD reconciliation |
| `GET` | `/api/clinics/<clinic_id>/days/<YYYY-MM-DD>/analytics/` | Deterministic analytics |
| `GET` | `/api/clinics/<clinic_id>/days/<YYYY-MM-DD>/narrative/` | LLM narrative, grounded against the two reports above |

### `POST .../ingest/`

Body: a JSON array of visit rows matching the schema in the brief (or
`{"rows": [...]}`). Every row is validated independently — a malformed row
never fails the whole batch.

```json
{
  "day_id": 3,
  "clinic_id": "CLN-KNP-014",
  "log_date": "2026-07-27",
  "accepted": 18,
  "rejected": [
    {
      "row_index": 18,
      "visit_id": "V-20260727-019",
      "field": "payment_mode",
      "error": "'payment_mode' is required but missing"
    }
  ]
}
```
Status `201` on success (even with some rows rejected), `400` if the body
isn't a JSON array at all.

### `GET .../reconciliation/`

```json
{
  "clinic_id": "CLN-KNP-014",
  "date": "2026-07-27",
  "visit_count": 18,
  "outstanding_visit_count": 3,
  "refund_count": 0,
  "total_billed_paise": 319000,
  "total_collected_paise": 317200,
  "total_outstanding_paise": 1800,
  "total_refunds_paise": 0,
  "collected_pct_of_billed": 99,
  "by_payment_mode": {
    "cash": {"billed_paise": 127500, "collected_paise": 127000, "outstanding_paise": 500, "refunds_paise": 0},
    "card": {"billed_paise": 83500, "collected_paise": 82700, "outstanding_paise": 800, "refunds_paise": 0},
    "upi":  {"billed_paise": 108000, "collected_paise": 107500, "outstanding_paise": 500, "refunds_paise": 0}
  }
}
```
`404` if that clinic/date hasn't been ingested yet.

### `GET .../analytics/`

```json
{
  "clinic_id": "CLN-KNP-014",
  "date": "2026-07-27",
  "revenue_by_hour": [{"hour": 9, "revenue_paise": 9000}, "..."],
  "peak_hour": {"hour": 13, "revenue_paise": 76000},
  "top_medicines_by_qty": [{"drug_name": "OMEPRAZOLE", "qty": 18}, "..."],
  "top_medicines_by_revenue": [{"drug_name": "ATORVASTATIN", "revenue_paise": 120000}, "..."]
}
```

### `GET .../narrative/`

```json
{
  "narrative": "Billed ₹3,190 across 18 visits, collected ₹3,172 (99%)...",
  "traced_figures": [{"text": "₹3,190", "field": "total_billed"}, "..."],
  "source": "llm",
  "rejection_reason": null
}
```
`source` is `"llm"` when Mistral's response passed grounding, or
`"fallback_template"` when it didn't (see below) — `rejection_reason`
explains why.

## Design decisions worth knowing about

The brief leaves several things to the candidate's judgment. Here's what I
chose and why (also documented as comments next to the code):

- **Billed / collected / outstanding** are computed only from non-refund
  visits — they answer "how much of today's *sales* came in". A refund is
  money paid back out for a *previous* sale, so it's tracked in its own
  `refunds` bucket rather than netted into `collected`; otherwise a
  refund-only day (like the 25 Jul sample) would show negative collections
  instead of the "nothing sold, ₹490 refunded" reality.
- A visit's billed amount is `(line-item total) − discount_paise`.
  `outstanding` is `max(billed − paid, 0)` **per visit**, so an overpayment
  on one visit can't cancel out a shortfall on another when summed.
- **Analytics** (revenue-by-hour, medicine rankings) also only look at
  non-refund visits, and medicine revenue uses the gross per-line amount
  (`qty × unit_price_paise`) rather than trying to prorate a visit-level
  discount across its line items.
- `drug_name` is used exactly as logged — no fuzzy matching. The sample
  data's `PARACETMOL` typo (alongside `PARACETAMOL`) shows up as two
  separate ranking entries. That's a front-desk data-quality issue to flag,
  not something this layer should silently "fix" and risk masking real
  distinctions.
- Timestamps are bucketed by their **UTC hour** as stored — the schema
  gives no clinic timezone to convert to.
- A row whose `timestamp` falls outside the date it's being ingested into
  is rejected (field `timestamp`), same as any other malformed row.

## How ingestion keeps data consistent on update

`billing/services/ingestion.py` is the only place billing rows are written.
Re-ingesting the same `(clinic_id, date)` — e.g. a corrected re-upload —
never produces duplicates or a half-updated state:

1. Every row in the new log is validated independently first, in memory.
   Nothing touches the database during validation.
2. The old rows for that `(clinic_id, date)` (if any) are deleted and the
   newly-validated rows are inserted **inside one `transaction.atomic()`
   block**, with `select_for_update()` on the `BillingDay` row to serialize
   concurrent ingests of the same day.
3. If anything raises partway through that block, Django rolls the whole
   transaction back — the previous day's data is left exactly as it was,
   never a mix of old and new rows.

This is covered by
`backend/billing/tests/test_ingestion.py::test_reingesting_the_same_day_replaces_rather_than_duplicates`
and `test_reingesting_a_corrected_day_drops_previously_stored_bad_state`.

## Narrative grounding, in more detail

`billing/services/narrative.py` builds a **closed list** of figures (with
their exact display strings, e.g. `"₹3,190"`, `"99%"`, `"OMEPRAZOLE"`) from
the reconciliation + analytics reports, and that list is the *only* thing
the model is told about. Mistral is asked to return structured JSON:
`{"narrative": ..., "traced_figures": [{"text": ..., "field": ...}]}`.

Before that response is ever shown to the clinic owner, it's checked:

- does it parse as that JSON shape at all?
- does every `traced_figures` entry point at a real field, with `text`
  matching that field's actual value and appearing verbatim in the
  narrative?
- does every number-like token *in the narrative text itself* trace back to
  an allowed figure?

Any failure — bad JSON, an invented number, a timeout, a missing API key,
a non-200 response — falls back to `_fallback_narrative()`, a template
built directly from the same figures. It literally cannot contain a number
that isn't in the report, and the request never crashes or 500s. This is
exercised in `backend/billing/tests/test_narrative.py` with a well-grounded
response, an invented number, malformed JSON, and a simulated API failure.

## Tests

- `billing/tests/test_validation.py` — row-level schema validation
- `billing/tests/test_ingestion.py` — batch ingestion, partial rejection,
  the update-consistency guarantee, out-of-range timestamps
- `billing/tests/test_reports.py` — reconciliation & analytics, checked
  against totals computed independently (not by reusing the app's own
  code) from the actual sample files, including the all-refund day and the
  empty day
- `billing/tests/test_narrative.py` — grounding validation and all its
  failure/fallback paths, with the Mistral call mocked
- `billing/tests/test_views.py` — the HTTP endpoints end to end

```bash
cd backend && python manage.py test billing
```
