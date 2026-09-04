from __future__ import annotations

import json
import logging
from pathlib import Path

from rag_platform.config import GenerationSettings
from rag_platform.generation.llm import OllamaClient
from rag_platform.observability import StructuredJsonFormatter, reset_request_id, set_request_id

ROOT = Path(__file__).resolve().parents[1]


def test_structured_log_schema_drops_unapproved_content() -> None:
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "completed", (), None)
        record.tenant_id = "tenant-456"
        record.user_content = "must-not-appear"
        payload = json.loads(StructuredJsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert set(payload) == {
        "timestamp",
        "level",
        "service",
        "request_id",
        "tenant_id",
        "trace_id",
        "message",
    }
    assert payload["request_id"] == "request-123"
    assert payload["tenant_id"] == "tenant-456"
    assert "must-not-appear" not in json.dumps(payload)


def test_ollama_metrics_are_derived_from_server_token_counts() -> None:
    client = OllamaClient(GenerationSettings())
    client._record_metrics({"eval_count": 50, "eval_duration": 2_000_000_000})
    assert client.last_metrics == {"generated_tokens": 50.0, "tokens_per_second": 25.0}


def test_all_dashboards_are_valid_json() -> None:
    dashboard_dir = ROOT / "helm" / "observability" / "dashboards"
    dashboards = {path.stem: json.loads(path.read_text()) for path in dashboard_dir.glob("*.json")}
    assert set(dashboards) == {"platform", "rag", "ingestion", "gpu"}
    assert all(dashboard["panels"] for dashboard in dashboards.values())
