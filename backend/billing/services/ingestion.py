"""
Ingests a raw billing log for one clinic-day.

Consistency guarantee: ingesting the same (clinic_id, log_date) twice never
leaves duplicate or half-updated data. The old rows for that day (if any)
and the new ones are swapped inside a single DB transaction, so a request
that fails partway through leaves the previous day's data intact rather
than a mixed state.
"""
from django.db import transaction

from billing.models import BillingDay, BillingRow
from billing.validation import validate_row


def ingest_billing_log(clinic_id, log_date, raw_rows):
    """
    Validates every row in `raw_rows`, then atomically replaces whatever was
    previously stored for (clinic_id, log_date) with the rows that passed.

    Returns a dict: {accepted: int, rejected: [ {row_index, visit_id,
    field, error}, ... ]}. Malformed rows never abort the whole batch --
    each is reported individually and excluded from storage.
    """
    if not isinstance(raw_rows, list):
        raise ValueError("billing log must be a JSON array of visit rows")

    cleaned_rows = []
    rejected = []
    seen_visit_ids = set()

    for index, raw_row in enumerate(raw_rows):
        cleaned, error = validate_row(raw_row, seen_visit_ids)
        if error is not None:
            rejected.append({"row_index": index, **error})
            continue
        if cleaned["clinic_id"] != clinic_id:
            seen_visit_ids.discard(cleaned["visit_id"])
            rejected.append(
                {
                    "row_index": index,
                    "visit_id": cleaned["visit_id"],
                    "field": "clinic_id",
                    "error": (
                        f"row's clinic_id '{cleaned['clinic_id']}' does not match "
                        f"the requested clinic_id '{clinic_id}'"
                    ),
                }
            )
            continue
        if cleaned["timestamp"].date() != log_date:
            seen_visit_ids.discard(cleaned["visit_id"])
            rejected.append(
                {
                    "row_index": index,
                    "visit_id": cleaned["visit_id"],
                    "field": "timestamp",
                    "error": (
                        f"timestamp '{cleaned['timestamp'].isoformat()}' is not on the "
                        f"ingested date {log_date.isoformat()}"
                    ),
                }
            )
            continue
        cleaned_rows.append(cleaned)

    with transaction.atomic():
        day, _ = BillingDay.objects.select_for_update().get_or_create(
            clinic_id=clinic_id, log_date=log_date
        )
        day.rows.all().delete()
        day.rejected_rows = rejected
        day.save(update_fields=["rejected_rows", "ingested_at"])

        BillingRow.objects.bulk_create(
            [
                BillingRow(
                    day=day,
                    visit_id=row["visit_id"],
                    timestamp=row["timestamp"],
                    doctor_id=row["doctor_id"],
                    line_items=row["line_items"],
                    payment_mode=row["payment_mode"],
                    amount_paid_paise=row["amount_paid_paise"],
                    discount_paise=row["discount_paise"],
                    is_refund=row["is_refund"],
                )
                for row in cleaned_rows
            ]
        )

    return {
        "day_id": day.id,
        "clinic_id": clinic_id,
        "log_date": log_date.isoformat(),
        "accepted": len(cleaned_rows),
        "rejected": rejected,
    }
