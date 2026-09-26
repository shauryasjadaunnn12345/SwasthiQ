import json
from datetime import datetime

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from billing.models import BillingDay
from billing.services.analytics import compute_analytics
from billing.services.ingestion import ingest_billing_log
from billing.services.narrative import generate_narrative
from billing.services.reconciliation import compute_reconciliation


def _parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise Http404(f"'{date_str}' is not a valid YYYY-MM-DD date")


def _get_day(clinic_id, date_str):
    log_date = _parse_date(date_str)
    return get_object_or_404(BillingDay, clinic_id=clinic_id, log_date=log_date)


@api_view(["POST"])
def ingest_view(request, clinic_id, date_str):
    log_date = _parse_date(date_str)
    raw_rows = request.data
    if isinstance(raw_rows, dict) and "rows" in raw_rows:
        raw_rows = raw_rows["rows"]
    try:
        result = ingest_billing_log(clinic_id, log_date, raw_rows)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    return Response(result, status=201)


@api_view(["GET"])
def reconciliation_view(request, clinic_id, date_str):
    day = _get_day(clinic_id, date_str)
    return Response(compute_reconciliation(day))


@api_view(["GET"])
def analytics_view(request, clinic_id, date_str):
    day = _get_day(clinic_id, date_str)
    return Response(compute_analytics(day))


@api_view(["GET"])
def narrative_view(request, clinic_id, date_str):
    day = _get_day(clinic_id, date_str)
    reconciliation = compute_reconciliation(day)
    analytics = compute_analytics(day)
    result = generate_narrative(reconciliation, analytics)
    return Response(result)


@api_view(["GET"])
def days_view(request, clinic_id):
    days = BillingDay.objects.filter(clinic_id=clinic_id).order_by("-log_date")
    return Response(
        [
            {
                "date": d.log_date.isoformat(),
                "visit_count": d.rows.count(),
                "rejected_count": len(d.rejected_rows),
            }
            for d in days
        ]
    )
