import json
from datetime import date
from pathlib import Path

from django.test import TestCase

from billing.services.analytics import compute_analytics
from billing.services.ingestion import ingest_billing_log
from billing.services.reconciliation import compute_reconciliation

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "sample_data"


def load_sample(name):
    return json.loads((SAMPLE_DIR / name).read_text())


class ReconciliationTests(TestCase):
    def test_all_refund_day_has_zero_billed_and_the_full_refund_total(self):
        rows = load_sample("billing_log_2026-07-25.json")
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 25), rows)
        from billing.models import BillingDay

        day = BillingDay.objects.get(log_date=date(2026, 7, 25))
        report = compute_reconciliation(day)

        self.assertEqual(report["total_billed_paise"], 0)
        self.assertEqual(report["total_collected_paise"], 0)
        self.assertEqual(report["total_outstanding_paise"], 0)
        self.assertEqual(report["total_refunds_paise"], 24000 + 22000 + 3000)
        self.assertEqual(report["refund_count"], 3)
        self.assertEqual(report["visit_count"], 3)
        self.assertIsNone(report["collected_pct_of_billed"])

    def test_empty_day_is_all_zeros(self):
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 26), [])
        from billing.models import BillingDay

        day = BillingDay.objects.get(log_date=date(2026, 7, 26))
        report = compute_reconciliation(day)
        self.assertEqual(report["visit_count"], 0)
        self.assertEqual(report["total_billed_paise"], 0)
        self.assertIsNone(report["collected_pct_of_billed"])

    def test_normal_day_matches_independently_computed_totals(self):
        rows = load_sample("billing_log_2026-07-27.json")
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        from billing.models import BillingDay

        day = BillingDay.objects.get(log_date=date(2026, 7, 27))
        report = compute_reconciliation(day)

        self.assertEqual(report["visit_count"], 18)
        self.assertEqual(report["total_billed_paise"], 319000)
        self.assertEqual(report["total_collected_paise"], 317200)
        self.assertEqual(report["total_outstanding_paise"], 1800)
        self.assertEqual(report["outstanding_visit_count"], 3)
        self.assertEqual(report["total_refunds_paise"], 0)

        self.assertEqual(
            report["by_payment_mode"]["cash"],
            {"billed_paise": 127500, "collected_paise": 127000, "outstanding_paise": 500, "refunds_paise": 0},
        )
        self.assertEqual(
            report["by_payment_mode"]["card"],
            {"billed_paise": 83500, "collected_paise": 82700, "outstanding_paise": 800, "refunds_paise": 0},
        )
        self.assertEqual(
            report["by_payment_mode"]["upi"],
            {"billed_paise": 108000, "collected_paise": 107500, "outstanding_paise": 500, "refunds_paise": 0},
        )


class AnalyticsTests(TestCase):
    def test_normal_day_matches_independently_computed_analytics(self):
        rows = load_sample("billing_log_2026-07-27.json")
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        from billing.models import BillingDay

        day = BillingDay.objects.get(log_date=date(2026, 7, 27))
        report = compute_analytics(day)

        self.assertEqual(report["peak_hour"], {"hour": 13, "revenue_paise": 76000})

        by_qty = {r["drug_name"]: r["qty"] for r in report["top_medicines_by_qty"]}
        self.assertEqual(
            by_qty,
            {
                "OMEPRAZOLE": 18,
                "METFORMIN": 14,
                "PARACETAMOL": 11,
                "AMOXICILLIN": 11,
                "ATORVASTATIN": 10,
                "PARACETMOL": 2,
            },
        )
        self.assertEqual(report["top_medicines_by_qty"][0]["drug_name"], "OMEPRAZOLE")

        by_revenue = {r["drug_name"]: r["revenue_paise"] for r in report["top_medicines_by_revenue"]}
        self.assertEqual(
            by_revenue,
            {
                "ATORVASTATIN": 120000,
                "OMEPRAZOLE": 72000,
                "AMOXICILLIN": 66000,
                "METFORMIN": 42000,
                "PARACETAMOL": 22000,
                "PARACETMOL": 4000,
            },
        )
        self.assertEqual(report["top_medicines_by_revenue"][0]["drug_name"], "ATORVASTATIN")

        # A typo'd drug name is kept distinct rather than silently merged.
        self.assertIn("PARACETMOL", by_qty)
        self.assertIn("PARACETAMOL", by_qty)

    def test_all_refund_day_has_no_analytics(self):
        rows = load_sample("billing_log_2026-07-25.json")
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 25), rows)
        from billing.models import BillingDay

        day = BillingDay.objects.get(log_date=date(2026, 7, 25))
        report = compute_analytics(day)
        self.assertEqual(report["revenue_by_hour"], [])
        self.assertIsNone(report["peak_hour"])
        self.assertEqual(report["top_medicines_by_qty"], [])
