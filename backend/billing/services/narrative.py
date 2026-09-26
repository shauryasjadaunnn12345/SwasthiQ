"""
LLM narrative layer.

The deterministic reconciliation + analytics reports are the only source of
truth. This module:

1. Builds a closed list of "figures" the model is allowed to mention, each
   with the exact string it must appear as in the narrative.
2. Asks Mistral for a short WhatsApp-style summary as structured JSON:
   {"narrative": str, "traced_figures": [{"text": ..., "field": ...}]}.
3. Verifies the response before trusting it at all:
   - it must parse as the expected JSON shape,
   - every {text, field} pair must reference a real figure and match its
     expected display string,
   - every number-like token that actually appears in the narrative text
     must be accounted for by some traced figure.
4. Any failure at step 3 (bad JSON, invented number, API error, timeout)
   falls back to a deterministically generated narrative built directly
   from the figures -- so the response can never silently ship an invented
   number, and a broken model call never crashes the request.
"""
import json
import re

import requests
from django.conf import settings

NUMBER_TOKEN_RE = re.compile(
    r"₹?\s?\d[\d,]*(?:\.\d+)?\s?(?:am|pm)?%?", re.IGNORECASE
)


def _rupees(paise):
    rupees, remainder = divmod(paise, 100)
    whole = f"{rupees:,}"
    return f"{whole}.{remainder:02d}" if remainder else whole


def _hour_label(hour):
    period = "am" if hour < 12 else "pm"
    display_hour = hour % 12
    display_hour = 12 if display_hour == 0 else display_hour
    return f"{display_hour}{period}"


def build_figures(reconciliation, analytics):
    """Returns {key: {"display": str, "description": str}} -- the ONLY
    numbers the model is allowed to use, each with the exact text it must
    appear as."""
    figures = {
        "total_billed": {
            "display": f"₹{_rupees(reconciliation['total_billed_paise'])}",
            "description": "total billed today",
        },
        "total_collected": {
            "display": f"₹{_rupees(reconciliation['total_collected_paise'])}",
            "description": "total collected today",
        },
        "outstanding": {
            "display": f"₹{_rupees(reconciliation['total_outstanding_paise'])}",
            "description": "outstanding amount still pending",
        },
        "refunds": {
            "display": f"₹{_rupees(reconciliation['total_refunds_paise'])}",
            "description": "total refunded today",
        },
        "visit_count": {
            "display": str(reconciliation["visit_count"]),
            "description": "number of visits today",
        },
        "outstanding_visit_count": {
            "display": str(reconciliation["outstanding_visit_count"]),
            "description": "number of visits with an outstanding balance",
        },
        "refund_count": {
            "display": str(reconciliation["refund_count"]),
            "description": "number of refunds today",
        },
    }
    if reconciliation["collected_pct_of_billed"] is not None:
        figures["collected_pct"] = {
            "display": f"{reconciliation['collected_pct_of_billed']}%",
            "description": "collected as a percentage of billed",
        }
    if analytics["peak_hour"]:
        start = _hour_label(analytics["peak_hour"]["hour"])
        end = _hour_label((analytics["peak_hour"]["hour"] + 1) % 24)
        figures["peak_hour_label"] = {
            "display": f"{start}-{end}",
            "description": "the busiest hour window",
        }
        figures["peak_hour_revenue"] = {
            "display": f"₹{_rupees(analytics['peak_hour']['revenue_paise'])}",
            "description": "revenue in the busiest hour",
        }
    if analytics["top_medicines_by_qty"]:
        top = analytics["top_medicines_by_qty"][0]
        figures["top_qty_drug_name"] = {"display": top["drug_name"], "description": "top medicine by quantity"}
        figures["top_qty_drug_qty"] = {"display": f"{top['qty']} units", "description": "units sold of the top medicine by quantity"}
    if analytics["top_medicines_by_revenue"]:
        top = analytics["top_medicines_by_revenue"][0]
        figures["top_revenue_drug_name"] = {"display": top["drug_name"], "description": "top medicine by revenue"}
        figures["top_revenue_drug_revenue"] = {"display": f"₹{_rupees(top['revenue_paise'])}", "description": "revenue from the top medicine by revenue"}
    return figures


def _normalize(text):
    return re.sub(r"[^a-z0-9%]", "", text.lower())


def _extract_number_tokens(text):
    return [m.group(0) for m in NUMBER_TOKEN_RE.finditer(text)]


def _validate_llm_response(parsed, figures):
    if not isinstance(parsed, dict):
        return False, "response was not a JSON object"
    narrative = parsed.get("narrative")
    traced = parsed.get("traced_figures")
    if not isinstance(narrative, str) or not narrative.strip():
        return False, "missing or empty 'narrative' string"
    if not isinstance(traced, list):
        return False, "missing 'traced_figures' list"

    traced_number_tokens = set()
    for entry in traced:
        if not isinstance(entry, dict) or "text" not in entry or "field" not in entry:
            return False, "a traced_figures entry is missing 'text' or 'field'"
        if not isinstance(entry["text"], str) or not isinstance(entry["field"], str):
            return False, "traced_figures 'text' and 'field' must be strings"
        field = entry["field"]
        if field not in figures:
            return False, f"traced_figures references unknown field '{field}'"
        if _normalize(entry["text"]) != _normalize(figures[field]["display"]):
            return False, f"traced_figures text for '{field}' doesn't match the report value"
        if entry["text"] not in narrative:
            return False, f"traced_figures text for '{field}' doesn't appear verbatim in the narrative"
        traced_number_tokens.update(
            _normalize(token) for token in _extract_number_tokens(entry["text"])
        )

    for token in _extract_number_tokens(narrative):
        if _normalize(token) not in traced_number_tokens:
            return False, f"narrative contains a figure without a matching trace: '{token.strip()}'"

    return True, None


def _fallback_narrative(figures):
    """A template-built summary that can only ever use real report figures."""
    lines = [f"*EOD Summary*"]
    lines.append(
        f"Billed {figures['total_billed']['display']} across {figures['visit_count']['display']} visits, "
        f"collected {figures['total_collected']['display']}"
        + (f" ({figures['collected_pct']['display']})." if "collected_pct" in figures else ".")
    )
    if figures["outstanding"]["display"] != "₹0":
        lines.append(
            f"{figures['outstanding']['display']} is still outstanding "
            f"across {figures['outstanding_visit_count']['display']} visit(s)."
        )
    if figures["refunds"]["display"] != "₹0":
        lines.append(
            f"{figures['refunds']['display']} was refunded ({figures['refund_count']['display']})."
        )
    if "peak_hour_label" in figures:
        lines.append(
            f"Busiest hour: {figures['peak_hour_label']['display']}, "
            f"{figures['peak_hour_revenue']['display']} in revenue."
        )
    if "top_qty_drug_name" in figures:
        lines.append(
            f"Top mover by quantity: {figures['top_qty_drug_name']['display']} "
            f"({figures['top_qty_drug_qty']['display']})."
        )
    if "top_revenue_drug_name" in figures:
        lines.append(
            f"Top by revenue: {figures['top_revenue_drug_name']['display']} "
            f"({figures['top_revenue_drug_revenue']['display']})."
        )
    lines.append("Note: profit isn't shown -- cost price isn't part of this data.")
    narrative = "\n".join(lines)
    traced_fields = ["total_billed", "visit_count", "total_collected"]
    if "collected_pct" in figures:
        traced_fields.append("collected_pct")
    if figures["outstanding"]["display"] != "₹0":
        traced_fields.extend(("outstanding", "outstanding_visit_count"))
    if figures["refunds"]["display"] != "₹0":
        traced_fields.extend(("refunds", "refund_count"))
    if "peak_hour_label" in figures:
        traced_fields.extend(("peak_hour_label", "peak_hour_revenue"))
    if "top_qty_drug_name" in figures:
        traced_fields.extend(("top_qty_drug_name", "top_qty_drug_qty"))
    if "top_revenue_drug_name" in figures:
        traced_fields.extend(("top_revenue_drug_name", "top_revenue_drug_revenue"))
    traced = [
        {"text": figures[key]["display"], "field": key}
        for key in traced_fields
    ]
    return {"narrative": narrative, "traced_figures": traced, "source": "fallback_template"}


def _call_mistral(figures):
    if not settings.MISTRAL_API_KEY:
        raise RuntimeError("MISTRAL_API_KEY is not configured")

    figure_list = "\n".join(
        f"- {key}: {fig['display']}  ({fig['description']})" for key, fig in figures.items()
    )
    system_prompt = (
        "You write short, friendly WhatsApp messages for a clinic owner summarizing "
        "their end-of-day billing. You may ONLY use the numbers given to you below, "
        "copied EXACTLY as shown -- never compute, round, or invent any other number. "
        "If something isn't in the list (e.g. profit), say plainly that it isn't available "
        "rather than approximating it. Keep it to 3-5 short lines.\n\n"
        "Respond with ONLY a JSON object of this shape, no other text:\n"
        '{"narrative": "<the message>", "traced_figures": '
        '[{"text": "<exact substring of narrative>", "field": "<key from the list below>"}]}\n\n'
        f"Available figures:\n{figure_list}"
    )

    response = requests.post(
        settings.MISTRAL_API_URL,
        headers={
            "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.MISTRAL_MODEL,
            "messages": [{"role": "system", "content": system_prompt}],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        },
        timeout=20,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    return json.loads(content)


def generate_narrative(reconciliation, analytics):
    """
    Returns {"narrative": str, "traced_figures": [...], "source": "llm"|"fallback_template",
    "rejection_reason": str|None}.
    """
    figures = build_figures(reconciliation, analytics)

    try:
        parsed = _call_mistral(figures)
    except Exception as exc:  # network error, timeout, bad status, bad JSON, missing key...
        result = _fallback_narrative(figures)
        result["rejection_reason"] = f"model call failed: {exc}"
        return result

    ok, reason = _validate_llm_response(parsed, figures)
    if not ok:
        result = _fallback_narrative(figures)
        result["rejection_reason"] = f"model response rejected: {reason}"
        return result

    return {
        "narrative": parsed["narrative"],
        "traced_figures": parsed["traced_figures"],
        "source": "llm",
        "rejection_reason": None,
    }
