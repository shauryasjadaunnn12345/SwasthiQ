import json
from pathlib import Path

from django.test import TestCase

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "sample_data"


def load_sample_text(name):
    return (SAMPLE_DIR / name).read_text()


class ApiEndpointTests(TestCase):
    def test_ingest_then_fetch_reconciliation_and_analytics(self):
        body = load_sample_text("billing_log_2026-07-27.json")
        resp = self.client.post(
            "/api/clinics/CLN-KNP-014/days/2026-07-27/ingest/",
            data=body,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        payload = resp.json()
        self.assertEqual(payload["accepted"], 18)
        self.assertEqual(len(payload["rejected"]), 1)

        resp = self.client.get("/api/clinics/CLN-KNP-014/days/2026-07-27/reconciliation/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_billed_paise"], 319000)

        resp = self.client.get("/api/clinics/CLN-KNP-014/days/2026-07-27/analytics/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["peak_hour"]["hour"], 13)

        resp = self.client.get("/api/clinics/CLN-KNP-014/days/2026-07-27/narrative/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"], "fallback_template")
        self.assertIn("₹3,190", resp.json()["narrative"])

    def test_reconciliation_for_a_day_never_ingested_is_404(self):
        resp = self.client.get("/api/clinics/CLN-KNP-014/days/2099-01-01/reconciliation/")
        self.assertEqual(resp.status_code, 404)

    def test_days_listing_reflects_ingested_days(self):
        self.client.post(
            "/api/clinics/CLN-KNP-014/days/2026-07-25/ingest/",
            data=load_sample_text("billing_log_2026-07-25.json"),
            content_type="application/json",
        )
        resp = self.client.get("/api/clinics/CLN-KNP-014/days/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [{"date": "2026-07-25", "visit_count": 3, "rejected_count": 0}])

    def test_ingest_rejects_a_non_array_body(self):
        resp = self.client.post(
            "/api/clinics/CLN-KNP-014/days/2026-07-27/ingest/",
            data=json.dumps({"not": "a list"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
