"""Unit tests for Gemini Assistant, security validation, and function calling."""

from unittest.mock import MagicMock, patch
import pytest

from src.llm.gemini_client import GeminiClientManager
from src.llm.orchestrator import GeminiOrchestrator
from src.llm.tools import (
    APPROVED_TOOLS_MAP,
    get_revenue_summary,
    validate_country_param,
    validate_date_param,
    validate_limit,
)
from src.utils.exceptions import ConfigurationError, SecurityViolationError


def test_tool_argument_date_validation():
    """Verify that invalid date formats are rejected with SecurityViolationError."""
    assert validate_date_param("start_date", "2023-01-15") is not None
    assert validate_date_param("start_date", None) is None

    with pytest.raises(SecurityViolationError):
        validate_date_param("start_date", "15-01-2023")  # Non-ISO format

    with pytest.raises(SecurityViolationError):
        validate_date_param("start_date", "2023-99-99")  # Invalid calendar date

    with pytest.raises(SecurityViolationError):
        validate_date_param("start_date", "2023-01-01; DROP TABLE orders;--")  # SQL injection attempt


def test_tool_argument_country_sanitization():
    """Verify country sanitization blocks SQL injection attempts."""
    assert validate_country_param("United Kingdom") == "United Kingdom"
    assert validate_country_param("All") is None
    assert validate_country_param(None) is None

    with pytest.raises(SecurityViolationError):
        validate_country_param("UK' OR '1'='1")


def test_validate_limit_clamping():
    """Verify limit integer is clamped within safe bounds (1 to 50)."""
    assert validate_limit(10) == 10
    assert validate_limit(999, max_limit=50) == 50
    assert validate_limit(-5) == 1
    assert validate_limit("invalid", default=15) == 15


def test_unauthorized_tool_rejected():
    """Verify that attempting to invoke an unapproved tool raises SecurityViolationError."""
    mock_client = MagicMock()
    # Mock Gemini response requesting unauthorized tool 'execute_raw_sql'
    mock_fc = MagicMock()
    mock_fc.name = "execute_raw_sql"
    mock_fc.args = {"query": "SELECT * FROM orders"}

    mock_resp = MagicMock()
    mock_resp.function_calls = [mock_fc]
    mock_client.models.generate_content.return_value = mock_resp

    mock_mgr = MagicMock(spec=GeminiClientManager)
    mock_mgr.get_client.return_value = mock_client
    mock_mgr.model_name = "gemini-3.8-flash"

    orchestrator = GeminiOrchestrator(client_manager=mock_mgr)
    result = orchestrator.process_query("Execute this SQL command")

    assert "Security Violation Blocked" in result["answer"]
    assert result["tool_called"] is None


def test_orchestrator_handles_missing_api_key():
    """Verify graceful handling when GEMINI_API_KEY is missing without throwing unhandled exceptions."""
    mock_mgr = MagicMock(spec=GeminiClientManager)
    mock_mgr.get_client.side_effect = ConfigurationError("GEMINI_API_KEY is not configured.")

    orchestrator = GeminiOrchestrator(client_manager=mock_mgr)
    result = orchestrator.process_query("What is our net revenue?")

    assert "Google Gemini API Key Not Configured" in result["answer"]
    assert result["error"] is not None


def test_orchestrator_with_mocked_gemini_tool_call():
    """Verify full tool execution cycle with mocked Google GenAI response."""
    mock_client = MagicMock()

    # Step 1: Model requests tool call 'get_revenue_summary'
    mock_fc = MagicMock()
    mock_fc.name = "get_revenue_summary"
    mock_fc.args = {"country": "United Kingdom"}

    first_resp = MagicMock()
    first_resp.function_calls = [mock_fc]
    candidate = MagicMock()
    candidate.content = MagicMock()
    first_resp.candidates = [candidate]

    # Step 2: Model returns synthesized answer after receiving tool data
    second_resp = MagicMock()
    second_resp.text = "The net revenue for United Kingdom is $50,000 across 1,200 orders."

    mock_client.models.generate_content.side_effect = [first_resp, second_resp]

    mock_mgr = MagicMock(spec=GeminiClientManager)
    mock_mgr.get_client.return_value = mock_client
    mock_mgr.model_name = "gemini-3.8-flash"

    with patch("src.llm.tools.AnalyticsService.get_executive_kpis") as mock_kpis:
        mock_kpis.return_value = {
            "gross_sales": 55000.0,
            "returns_amount": 5000.0,
            "net_revenue": 50000.0,
            "completed_orders": 1200,
            "unique_customers": 450,
            "average_order_value": 41.67,
            "repeat_customers": 180,
            "repeat_purchase_rate": 40.0,
        }

        orchestrator = GeminiOrchestrator(client_manager=mock_mgr)
        res = orchestrator.process_query("What is the revenue for United Kingdom?")

        assert res["tool_called"] == "get_revenue_summary"
        assert res["tool_arguments"] == {"country": "United Kingdom"}
        assert "50,000" in res["answer"]
        assert res["tool_output"] is not None
