import json
from datetime import date
from pathlib import Path

from django.test import TestCase

from billing.models import BillingDay, BillingRow
from billing.services.ingestion import ingest_billing_log

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "sample_data"


def load_sample(name):
    return json.loads((SAMPLE_DIR / name).read_text())


class IngestBillingLogTests(TestCase):
    def test_all_refund_day_is_accepted_and_stored(self):
        rows = load_sample("billing_log_2026-07-25.json")
        result = ingest_billing_log("CLN-KNP-014", date(2026, 7, 25), rows)
        self.assertEqual(result["accepted"], 3)
        self.assertEqual(result["rejected"], [])

    def test_empty_day_is_accepted_with_zero_rows(self):
        result = ingest_billing_log("CLN-KNP-014", date(2026, 7, 26), [])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(BillingDay.objects.get(log_date=date(2026, 7, 26)).rows.count(), 0)

    def test_the_one_malformed_row_in_the_sample_day_is_rejected_not_fatal(self):
        rows = load_sample("billing_log_2026-07-27.json")
        result = ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        self.assertEqual(result["accepted"], 18)
        self.assertEqual(len(result["rejected"]), 1)
        self.assertEqual(result["rejected"][0]["visit_id"], "V-20260727-019")
        self.assertEqual(result["rejected"][0]["field"], "payment_mode")

    def test_reingesting_the_same_day_replaces_rather_than_duplicates(self):
        rows = load_sample("billing_log_2026-07-27.json")
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        first_count = BillingRow.objects.filter(day__log_date=date(2026, 7, 27)).count()

        # Re-ingest the identical file again.
        ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        second_count = BillingRow.objects.filter(day__log_date=date(2026, 7, 27)).count()

        self.assertEqual(first_count, second_count)
        self.assertEqual(BillingDay.objects.filter(log_date=date(2026, 7, 27)).count(), 1)

    def test_reingesting_a_corrected_day_drops_previously_stored_bad_state(self):
        ingest_billing_log(
            "CLN-KNP-014",
            date(2026, 7, 27),
            [
                {
                    "clinic_id": "CLN-KNP-014",
                    "visit_id": "V-OLD",
                    "timestamp": "2026-07-27T09:00:00Z",
                    "doctor_id": "DOC-1",
                    "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 100}],
                    "payment_mode": "cash",
                    "amount_paid_paise": 100,
                    "discount_paise": 0,
                    "is_refund": False,
                }
            ],
        )
        # A corrected re-upload for the same day, without V-OLD.
        ingest_billing_log(
            "CLN-KNP-014",
            date(2026, 7, 27),
            [
                {
                    "clinic_id": "CLN-KNP-014",
                    "visit_id": "V-NEW",
                    "timestamp": "2026-07-27T09:00:00Z",
                    "doctor_id": "DOC-1",
                    "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 100}],
                    "payment_mode": "cash",
                    "amount_paid_paise": 100,
                    "discount_paise": 0,
                    "is_refund": False,
                }
            ],
        )
        day = BillingDay.objects.get(clinic_id="CLN-KNP-014", log_date=date(2026, 7, 27))
        visit_ids = list(day.rows.values_list("visit_id", flat=True))
        self.assertEqual(visit_ids, ["V-NEW"])

    def test_a_row_dated_outside_the_ingested_day_is_rejected(self):
        rows = [
            {
                "clinic_id": "CLN-KNP-014",
                "visit_id": "V-WRONG-DAY",
                "timestamp": "2026-07-28T09:00:00Z",
                "line_items": [{"drug_name": "X", "qty": 1, "unit_price_paise": 100}],
                "payment_mode": "cash",
                "amount_paid_paise": 100,
                "discount_paise": 0,
                "is_refund": False,
            }
        ]
        result = ingest_billing_log("CLN-KNP-014", date(2026, 7, 27), rows)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["rejected"][0]["field"], "timestamp")

    def test_unhashable_payment_mode_rejects_only_that_row(self):
        valid_row = load_sample("billing_log_2026-07-27.json")[0]
        invalid_row = {**valid_row, "visit_id": "V-BAD-MODE", "payment_mode": []}
        valid_row = {**valid_row, "visit_id": "V-GOOD-MODE"}

        result = ingest_billing_log(
            "CLN-KNP-014", date(2026, 7, 27), [invalid_row, valid_row]
        )

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"][0]["field"], "payment_mode")

    def test_rejected_clinic_row_does_not_reserve_visit_id(self):
        source_row = load_sample("billing_log_2026-07-27.json")[0]
        wrong_clinic = {**source_row, "clinic_id": "OTHER", "visit_id": "V-REUSED"}
        valid_row = {**source_row, "visit_id": "V-REUSED"}

        result = ingest_billing_log(
            "CLN-KNP-014", date(2026, 7, 27), [wrong_clinic, valid_row]
        )

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"][0]["field"], "clinic_id")

    def test_rejected_date_row_does_not_reserve_visit_id(self):
        source_row = load_sample("billing_log_2026-07-27.json")[0]
        wrong_date = {
            **source_row,
            "visit_id": "V-REUSED-DATE",
            "timestamp": "2026-07-28T09:00:00Z",
        }
        valid_row = {**source_row, "visit_id": "V-REUSED-DATE"}

        result = ingest_billing_log(
            "CLN-KNP-014", date(2026, 7, 27), [wrong_date, valid_row]
        )

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"][0]["field"], "timestamp")
