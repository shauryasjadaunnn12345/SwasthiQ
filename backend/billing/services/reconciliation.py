"""
Deterministic EOD reconciliation.

Design choices (documented here since the brief leaves them to us):

* "Billed" and "collected" are computed only from non-refund visits -- they
  answer "how much of today's *sales* came in". Money paid back out on a
  refund is tracked in its own `refunds` bucket rather than netted into
  `collected`, so a refund-only day doesn't read as negative collections.
* A visit's billed amount is (line-item total - discount_paise), i.e. what
  the patient actually owed after the discount applied to that visit.
* "Outstanding" is billed-minus-paid, clamped at zero per visit, so an
  overpayment on one visit never cancels out a shortfall on another.
* Everything is kept in integer paise; only the API layer/README talk in
  rupees.
"""
from collections import defaultdict

PAYMENT_MODES = ("cash", "card", "upi")


def _empty_mode_bucket():
    return {"billed_paise": 0, "collected_paise": 0, "outstanding_paise": 0, "refunds_paise": 0}


def compute_reconciliation(day):
    """`day` is a BillingDay with its `rows` prefetched or queryable."""
    by_mode = {mode: _empty_mode_bucket() for mode in PAYMENT_MODES}

    total_billed = 0
    total_collected = 0
    total_outstanding = 0
    total_refunds = 0
    outstanding_visit_count = 0
    refund_count = 0

    rows = list(day.rows.all())

    for row in rows:
        mode_bucket = by_mode[row.payment_mode]
        gross = sum(item["qty"] * item["unit_price_paise"] for item in row.line_items)
        net_billed = gross - row.discount_paise

        if row.is_refund:
            refund_amount = -row.amount_paid_paise
            mode_bucket["refunds_paise"] += refund_amount
            total_refunds += refund_amount
            refund_count += 1
            continue

        outstanding = max(net_billed - row.amount_paid_paise, 0)

        mode_bucket["billed_paise"] += net_billed
        mode_bucket["collected_paise"] += row.amount_paid_paise
        mode_bucket["outstanding_paise"] += outstanding

        total_billed += net_billed
        total_collected += row.amount_paid_paise
        total_outstanding += outstanding
        if outstanding > 0:
            outstanding_visit_count += 1

    collected_pct_of_billed = (
        round((total_collected / total_billed) * 100) if total_billed > 0 else None
    )

    return {
        "clinic_id": day.clinic_id,
        "date": day.log_date.isoformat(),
        "visit_count": len(rows),
        "outstanding_visit_count": outstanding_visit_count,
        "refund_count": refund_count,
        "total_billed_paise": total_billed,
        "total_collected_paise": total_collected,
        "total_outstanding_paise": total_outstanding,
        "total_refunds_paise": total_refunds,
        "collected_pct_of_billed": collected_pct_of_billed,
        "by_payment_mode": by_mode,
    }
