from django.test import SimpleTestCase

from billing.validation import validate_row


def base_row(**overrides):
    row = {
        "clinic_id": "CLN-KNP-014",
        "visit_id": "V-1",
        "timestamp": "2026-07-27T10:00:00Z",
        "doctor_id": "DOC-1",
        "line_items": [{"drug_name": "PARACETAMOL", "qty": 2, "unit_price_paise": 2000}],
        "payment_mode": "cash",
        "amount_paid_paise": 4000,
        "discount_paise": 0,
        "is_refund": False,
    }
    row.update(overrides)
    return row


class ValidateRowTests(SimpleTestCase):
    def test_accepts_a_well_formed_row(self):
        cleaned, error = validate_row(base_row(), set())
        self.assertIsNone(error)
        self.assertEqual(cleaned["gross_paise"], 4000)

    def test_missing_payment_mode_is_rejected_specifically(self):
        row = base_row()
        del row["payment_mode"]
        cleaned, error = validate_row(row, set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "payment_mode")

    def test_invalid_payment_mode_enum_is_rejected(self):
        cleaned, error = validate_row(base_row(payment_mode="paytm"), set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "payment_mode")

    def test_unhashable_payment_mode_is_rejected_without_raising(self):
        for payment_mode in ([], {}):
            with self.subTest(payment_mode=payment_mode):
                cleaned, error = validate_row(base_row(payment_mode=payment_mode), set())
                self.assertIsNone(cleaned)
                self.assertEqual(error["field"], "payment_mode")

    def test_duplicate_visit_id_is_rejected(self):
        seen = {"V-1"}
        cleaned, error = validate_row(base_row(), seen)
        self.assertIsNone(cleaned)
        self.assertIn("duplicate", error["error"])

    def test_refund_with_positive_amount_is_rejected(self):
        cleaned, error = validate_row(
            base_row(is_refund=True, amount_paid_paise=4000), set()
        )
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "amount_paid_paise")

    def test_non_refund_with_negative_amount_is_rejected(self):
        cleaned, error = validate_row(
            base_row(is_refund=False, amount_paid_paise=-100), set()
        )
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "amount_paid_paise")

    def test_refund_row_accepted(self):
        cleaned, error = validate_row(
            base_row(is_refund=True, amount_paid_paise=-4000), set()
        )
        self.assertIsNone(error)
        self.assertTrue(cleaned["is_refund"])

    def test_discount_exceeding_gross_is_rejected(self):
        cleaned, error = validate_row(base_row(discount_paise=999999), set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "discount_paise")

    def test_empty_line_items_is_rejected(self):
        cleaned, error = validate_row(base_row(line_items=[]), set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "line_items")

    def test_non_positive_qty_is_rejected(self):
        row = base_row(
            line_items=[{"drug_name": "X", "qty": 0, "unit_price_paise": 100}]
        )
        cleaned, error = validate_row(row, set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "line_items")

    def test_timestamp_without_offset_is_rejected(self):
        cleaned, error = validate_row(base_row(timestamp="2026-07-27T10:00:00"), set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "timestamp")

    def test_malformed_row_that_is_not_an_object(self):
        cleaned, error = validate_row("not a row", set())
        self.assertIsNone(cleaned)
        self.assertEqual(error["field"], "_row")
