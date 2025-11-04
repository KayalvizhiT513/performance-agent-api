import json
import sys
import types
import unittest
from unittest.mock import patch

if "groq" not in sys.modules:
    groq_module = types.ModuleType("groq")

    class Groq:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        class chat:  # type: ignore
            class completions:  # type: ignore
                @staticmethod
                def create(*_args, **_kwargs):
                    raise RuntimeError("Groq client stub should not be invoked in tests")

    groq_module.Groq = Groq
    sys.modules["groq"] = groq_module

from app.orchestrator import orchestrate_query


class DummyResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload

    def json(self):
        return self._payload


class OrchestratorIntegrationTests(unittest.TestCase):
    @patch("app.orchestrator.run_nl_query")
    @patch("app.orchestrator.call_groq")
    def test_get_data_flow_uses_nl_executor(self, mock_call_groq, mock_run_nl_query):
        mock_call_groq.return_value = json.dumps({"intent": "get_data"})
        mock_run_nl_query.return_value = {
            "sql": "SELECT 1",
            "params": None,
            "rows": [{"id": 1}],
        }

        result = orchestrate_query("show me data")

        mock_run_nl_query.assert_called_once_with("show me data")
        self.assertEqual(result["intent"], "get_data")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["preview"], [{"id": 1}])

    @patch("app.orchestrator.requests.post")
    @patch("app.orchestrator.run_nl_query")
    @patch("app.orchestrator.call_groq")
    def test_compute_metric_flow_uses_nl_executor_and_formula_api(self, mock_call_groq, mock_run_nl_query, mock_requests_post):
        mock_call_groq.return_value = json.dumps({"intent": "compute_metric", "metric": "sharpe"})
        mock_run_nl_query.return_value = {
            "sql": "SELECT date, return_value FROM returns",
            "params": None,
            "rows": [
                {"date": "2024-01-01", "return_value": 0.01},
                {"date": "2024-01-02", "return_value": 0.02},
            ],
        }
        mock_requests_post.return_value = DummyResponse({"value": 1.5, "methodology": "test"})

        result = orchestrate_query("compute sharpe")

        mock_run_nl_query.assert_called_once_with("compute sharpe")
        mock_requests_post.assert_called_once()
        self.assertEqual(result["intent"], "compute_metric")
        self.assertEqual(result["metric"], "sharpe")
        self.assertEqual(result["value"], 1.5)
        self.assertEqual(result["row_count"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
