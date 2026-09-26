"""
Validates one raw billing-log row against the schema in the assignment
brief and returns either a cleaned row or a specific, actionable error.

Deliberately independent of Django/DRF so it can be unit tested with plain
dicts and reused by both the ingestion endpoint and the test suite.
"""
from datetime import datetime, timezone

VALID_PAYMENT_MODES = {"cash", "card", "upi"}

REQUIRED_FIELDS = [
    "clinic_id",
    "visit_id",
    "timestamp",
    "line_items",
    "payment_mode",
    "amount_paid_paise",
    "is_refund",
]


class RowValidationError(Exception):
    def __init__(self, field, message):
        self.field = field
        self.message = message
        super().__init__(message)


def _parse_timestamp(value):
    try:
        # Accept the trailing "Z" that datetime.fromisoformat only started
        # supporting itself in 3.11+; normalize it ourselves for portability.
        text = value.replace("Z", "+00:00") if isinstance(value, str) else value
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        raise RowValidationError(
            "timestamp", f"'{value}' is not a valid ISO 8601 timestamp"
        ) from exc
    if dt.tzinfo is None:
        raise RowValidationError(
            "timestamp", "timestamp must include a UTC offset (e.g. trailing 'Z')"
        )
    return dt.astimezone(timezone.utc)


def _validate_line_items(raw_items):
    if not isinstance(raw_items, list) or len(raw_items) == 0:
        raise RowValidationError(
            "line_items", "line_items must be a non-empty array"
        )
    cleaned = []
    gross_paise = 0
    for i, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise RowValidationError("line_items", f"line_items[{i}] must be an object")
        drug_name = item.get("drug_name")
        qty = item.get("qty")
        unit_price = item.get("unit_price_paise")
        if not isinstance(drug_name, str) or not drug_name.strip():
            raise RowValidationError(
                "line_items", f"line_items[{i}].drug_name must be a non-empty string"
            )
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise RowValidationError(
                "line_items", f"line_items[{i}].qty must be a positive integer"
            )
        if (
            not isinstance(unit_price, int)
            or isinstance(unit_price, bool)
            or unit_price < 0
        ):
            raise RowValidationError(
                "line_items",
                f"line_items[{i}].unit_price_paise must be a non-negative integer",
            )
        cleaned.append(
            {
                "drug_name": drug_name.strip(),
                "qty": qty,
                "unit_price_paise": unit_price,
            }
        )
        gross_paise += qty * unit_price
    return cleaned, gross_paise


def validate_row(raw_row, seen_visit_ids):
    """
    Returns (cleaned_row: dict, None) on success, or (None, error: dict) on
    failure. `seen_visit_ids` is a set the caller mutates across the batch
    so duplicate visit_ids within one log are caught.
    """
    if not isinstance(raw_row, dict):
        return None, {"visit_id": None, "field": "_row", "error": "row is not a JSON object"}

    visit_id = raw_row.get("visit_id")

    try:
        for field in REQUIRED_FIELDS:
            if field not in raw_row:
                raise RowValidationError(field, f"'{field}' is required but missing")

        if not isinstance(visit_id, str) or not visit_id.strip():
            raise RowValidationError("visit_id", "visit_id must be a non-empty string")
        if visit_id in seen_visit_ids:
            raise RowValidationError("visit_id", f"duplicate visit_id '{visit_id}' in this log")

        clinic_id = raw_row.get("clinic_id")
        if not isinstance(clinic_id, str) or not clinic_id.strip():
            raise RowValidationError("clinic_id", "clinic_id must be a non-empty string")

        timestamp = _parse_timestamp(raw_row.get("timestamp"))

        payment_mode = raw_row.get("payment_mode")
        if not isinstance(payment_mode, str) or payment_mode not in VALID_PAYMENT_MODES:
            raise RowValidationError(
                "payment_mode",
                f"payment_mode must be one of {sorted(VALID_PAYMENT_MODES)}, got {payment_mode!r}",
            )

        is_refund = raw_row.get("is_refund")
        if not isinstance(is_refund, bool):
            raise RowValidationError("is_refund", "is_refund must be a boolean")

        amount_paid_paise = raw_row.get("amount_paid_paise")
        if not isinstance(amount_paid_paise, int) or isinstance(amount_paid_paise, bool):
            raise RowValidationError(
                "amount_paid_paise", "amount_paid_paise must be an integer (paise)"
            )

        discount_paise = raw_row.get("discount_paise", 0)
        if not isinstance(discount_paise, int) or isinstance(discount_paise, bool) or discount_paise < 0:
            raise RowValidationError(
                "discount_paise", "discount_paise must be a non-negative integer"
            )

        line_items, gross_paise = _validate_line_items(raw_row.get("line_items"))

        if discount_paise > gross_paise:
            raise RowValidationError(
                "discount_paise",
                f"discount_paise ({discount_paise}) exceeds the line-item total ({gross_paise})",
            )

        if is_refund and amount_paid_paise >= 0:
            raise RowValidationError(
                "amount_paid_paise",
                "is_refund=true requires a negative amount_paid_paise",
            )
        if not is_refund and amount_paid_paise < 0:
            raise RowValidationError(
                "amount_paid_paise",
                "amount_paid_paise cannot be negative unless is_refund=true",
            )

        seen_visit_ids.add(visit_id)

        return {
            "clinic_id": clinic_id,
            "visit_id": visit_id,
            "timestamp": timestamp,
            "doctor_id": raw_row.get("doctor_id") or "",
            "line_items": line_items,
            "gross_paise": gross_paise,
            "payment_mode": payment_mode,
            "amount_paid_paise": amount_paid_paise,
            "discount_paise": discount_paise,
            "is_refund": is_refund,
        }, None

    except RowValidationError as exc:
        return None, {
            "visit_id": visit_id if isinstance(visit_id, str) else None,
            "field": exc.field,
            "error": exc.message,
        }
