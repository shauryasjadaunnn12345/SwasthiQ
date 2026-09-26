"""
Deterministic analytics layer.

Design choices:

* Only non-refund visits contribute -- a refund event isn't a sale that
  happened during that hour, and the medicines on a refund's line items
  were already counted as moved on the day they were originally sold.
* "Revenue by hour" uses each visit's billed (post-discount) amount, not
  what was actually collected, so a partially-paid visit still shows up in
  full in the hour it happened.
* Medicine rankings use gross per-line revenue (qty * unit_price_paise).
  discount_paise is recorded per visit, not per line item, so there's no
  non-arbitrary way to prorate it across a visit's medicines -- documented
  here rather than silently guessed at.
* Timestamps are bucketed by their UTC hour as stored, since the schema
  gives no clinic timezone to convert to.
* drug_name is used exactly as logged (no fuzzy matching). A typo like
  "PARACETMOL" next to "PARACETAMOL" will show up as two separate entries
  -- that's a front-desk data-quality issue, not something this layer
  should silently "fix" and risk masking real distinctions.
"""
from collections import defaultdict


def compute_analytics(day):
    rows = [r for r in day.rows.all() if not r.is_refund]

    revenue_by_hour = defaultdict(int)
    qty_by_drug = defaultdict(int)
    revenue_by_drug = defaultdict(int)

    for row in rows:
        gross = sum(item["qty"] * item["unit_price_paise"] for item in row.line_items)
        net_billed = gross - row.discount_paise
        hour = row.timestamp.hour
        revenue_by_hour[hour] += net_billed

        for item in row.line_items:
            qty_by_drug[item["drug_name"]] += item["qty"]
            revenue_by_drug[item["drug_name"]] += item["qty"] * item["unit_price_paise"]

    revenue_by_hour_list = [
        {"hour": hour, "revenue_paise": revenue}
        for hour, revenue in sorted(revenue_by_hour.items())
    ]

    peak_hour = None
    if revenue_by_hour_list:
        peak = max(revenue_by_hour_list, key=lambda h: h["revenue_paise"])
        if peak["revenue_paise"] > 0:
            peak_hour = peak

    top_by_qty = sorted(
        ({"drug_name": name, "qty": qty} for name, qty in qty_by_drug.items()),
        key=lambda x: (-x["qty"], x["drug_name"]),
    )
    top_by_revenue = sorted(
        (
            {"drug_name": name, "revenue_paise": revenue}
            for name, revenue in revenue_by_drug.items()
        ),
        key=lambda x: (-x["revenue_paise"], x["drug_name"]),
    )

    return {
        "clinic_id": day.clinic_id,
        "date": day.log_date.isoformat(),
        "revenue_by_hour": revenue_by_hour_list,
        "peak_hour": peak_hour,
        "top_medicines_by_qty": top_by_qty,
        "top_medicines_by_revenue": top_by_revenue,
    }
