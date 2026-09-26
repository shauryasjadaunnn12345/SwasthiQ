import json
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from billing.services.narrative import build_figures, generate_narrative

RECONCILIATION = {
    "total_billed_paise": 4285000,
    "total_collected_paise": 3820000,
    "total_outstanding_paise": 465000,
    "total_refunds_paise": 60000,
    "visit_count": 18,
    "outstanding_visit_count": 3,
    "refund_count": 1,
    "collected_pct_of_billed": 89,
}
ANALYTICS = {
    "peak_hour": {"hour": 12, "revenue_paise": 840000},
    "top_medicines_by_qty": [{"drug_name": "PARACETAMOL", "qty": 142}],
    "top_medicines_by_revenue": [{"drug_name": "ATORVASTATIN", "revenue_paise": 648000}],
}


def mock_response(json_body, status=200):
    resp = Mock()
    resp.status_code = status
    resp.raise_for_status = Mock()
    resp.json.return_value = json_body
    return resp


@override_settings(MISTRAL_API_KEY="test-key")
class NarrativeGenerationTests(SimpleTestCase):
    def test_well_grounded_response_is_used_as_is(self):
        figures = build_figures(RECONCILIATION, ANALYTICS)
        narrative_text = (
            f"Billed {figures['total_billed']['display']}, "
            f"collected {figures['total_collected']['display']} "
            f"({figures['collected_pct']['display']})."
        )
        llm_body = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"narrative": "%s", "traced_figures": ['
                            '{"text": "%s", "field": "total_billed"},'
                            '{"text": "%s", "field": "total_collected"},'
                            '{"text": "%s", "field": "collected_pct"}]}'
                        )
                        % (
                            narrative_text,
                            figures["total_billed"]["display"],
                            figures["total_collected"]["display"],
                            figures["collected_pct"]["display"],
                        )
                    }
                }
            ]
        }
        with patch("billing.services.narrative.requests.post", return_value=mock_response(llm_body)):
            result = generate_narrative(RECONCILIATION, ANALYTICS)

        self.assertEqual(result["source"], "llm")
        self.assertIsNone(result["rejection_reason"])
        self.assertEqual(result["narrative"], narrative_text)

    def test_figures_preserve_nonzero_paise(self):
        reconciliation = {**RECONCILIATION, "total_billed_paise": 428501}
        figures = build_figures(reconciliation, ANALYTICS)

        self.assertEqual(figures["total_billed"]["display"], "₹4,285.01")

    def test_invented_number_triggers_fallback(self):
        llm_body = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"narrative": "Profit today was \\u20b912,345.", '
                            '"traced_figures": []}'
                        )
                    }
                }
            ]
        }
        with patch("billing.services.narrative.requests.post", return_value=mock_response(llm_body)):
            result = generate_narrative(RECONCILIATION, ANALYTICS)

        self.assertEqual(result["source"], "fallback_template")
        self.assertIn("matching trace", result["rejection_reason"])
        # The fallback must still only contain real figures.
        self.assertIn("₹42,850", result["narrative"])

    def test_number_without_a_matching_trace_triggers_fallback(self):
        figures = build_figures(RECONCILIATION, ANALYTICS)
        narrative_text = (
            f"Billed {figures['total_billed']['display']} across "
            f"{figures['visit_count']['display']} visits."
        )
        llm_body = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"narrative": narrative_text, "traced_figures": []}
                        )
                    }
                }
            ]
        }
        with patch("billing.services.narrative.requests.post", return_value=mock_response(llm_body)):
            result = generate_narrative(RECONCILIATION, ANALYTICS)

        self.assertEqual(result["source"], "fallback_template")
        self.assertIn("matching trace", result["rejection_reason"])

    def test_wrong_typed_trace_fields_trigger_fallback_not_a_crash(self):
        for trace in (
            {"text": [], "field": "total_billed"},
            {"text": "₹4,285", "field": []},
        ):
            with self.subTest(trace=trace):
                llm_body = {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "narrative": "Billed ₹4,285.",
                                        "traced_figures": [trace],
                                    }
                                )
                            }
                        }
                    ]
                }
                with patch(
                    "billing.services.narrative.requests.post",
                    return_value=mock_response(llm_body),
                ):
                    result = generate_narrative(RECONCILIATION, ANALYTICS)

                self.assertEqual(result["source"], "fallback_template")

    def test_malformed_json_from_model_triggers_fallback_not_a_crash(self):
        llm_body = {"choices": [{"message": {"content": "not json at all"}}]}
        with patch("billing.services.narrative.requests.post", return_value=mock_response(llm_body)):
            result = generate_narrative(RECONCILIATION, ANALYTICS)
        self.assertEqual(result["source"], "fallback_template")
        self.assertIsNotNone(result["rejection_reason"])

    def test_api_failure_triggers_fallback_not_a_crash(self):
        with patch("billing.services.narrative.requests.post", side_effect=ConnectionError("boom")):
            result = generate_narrative(RECONCILIATION, ANALYTICS)
        self.assertEqual(result["source"], "fallback_template")
        self.assertIn("model call failed", result["rejection_reason"])

    @override_settings(MISTRAL_API_KEY="")
    def test_missing_api_key_triggers_fallback_not_a_crash(self):
        result = generate_narrative(RECONCILIATION, ANALYTICS)
        self.assertEqual(result["source"], "fallback_template")

    def test_fallback_narrative_never_contains_untraced_numbers(self):
        zero_refund_reconciliation = {
            **RECONCILIATION,
            "total_refunds_paise": 0,
            "refund_count": 0,
        }
        figures = build_figures(zero_refund_reconciliation, ANALYTICS)
        from billing.services.narrative import _fallback_narrative, _validate_llm_response

        result = _fallback_narrative(figures)
        ok, reason = _validate_llm_response(result, figures)
        self.assertTrue(ok, reason)
        self.assertNotIn("refund_count", [item["field"] for item in result["traced_figures"]])
