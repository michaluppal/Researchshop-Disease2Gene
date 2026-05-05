"""Tests for trace persistence and semantic stage tags."""

import importlib
import json
import os
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def reset_tracer_module(monkeypatch):
    yield
    for name in ("TRACE_PMID", "TRACE_OUT_DIR", "TRACE_LIVE_FILE", "TRACE_FUNCTIONS"):
        monkeypatch.delenv(name, raising=False)

    from modules import pipeline_tracer

    importlib.reload(pipeline_tracer)


def _reload_tracer(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACE_PMID", "123")
    monkeypatch.setenv("TRACE_OUT_DIR", str(tmp_path / "partials"))
    monkeypatch.setenv("TRACE_LIVE_FILE", str(tmp_path / "live_events.jsonl"))
    monkeypatch.setenv("TRACE_FUNCTIONS", "1")

    from modules import pipeline_tracer

    return importlib.reload(pipeline_tracer)


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_worker_partial_uses_trace_out_dir_env_and_stage_id(monkeypatch, tmp_path):
    tracer = _reload_tracer(monkeypatch, tmp_path)

    with tracer.stage("grounding_check"):
        tracer.capture("grounding_check", pmid="123", outputs={"kept": 2})

    partial = tracer.flush_worker_partial()

    assert partial is not None
    assert partial.parent == tmp_path / "partials"
    events = _jsonl(partial)
    assert events[0]["node_id"] == "grounding_check"
    assert events[0]["stage_id"] == "grounding_check"


def test_collect_and_write_merges_live_stage_events(monkeypatch, tmp_path):
    tracer = _reload_tracer(monkeypatch, tmp_path)
    live_file = tmp_path / "live_events.jsonl"
    live_file.write_text(
        json.dumps({
            "node_id": "deterministic_scan",
            "stage_id": "deterministic_scan",
            "outputs": {"candidate_count": 4},
        }) + "\n",
        encoding="utf-8",
    )

    trace_path = tracer.collect_and_write("123", tmp_path / "trace_123.json")

    assert trace_path is not None
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert "deterministic_scan" in payload["nodes"]
    assert payload["nodes"]["deterministic_scan"]["stage_id"] == "deterministic_scan"


def test_collect_and_write_keeps_viewer_payload_shape(monkeypatch, tmp_path):
    tracer = _reload_tracer(monkeypatch, tmp_path)

    tracer.capture("pubmed_metadata", pmid="123", outputs={"retrieved_count": 1})
    trace_path = tracer.collect_and_write("123", tmp_path / "trace_123.json")

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "pmid",
        "generated_at",
        "node_count",
        "nodes",
        "function_event_count",
        "function_trace_path",
        "function_counts_by_stage",
        "function_counts_by_name",
    }
    assert payload["pmid"] == "123"
    assert payload["node_count"] == 1
    assert payload["nodes"]["pubmed_metadata"]["node_id"] == "pubmed_metadata"
    assert payload["function_event_count"] == 0
    assert payload["function_trace_path"] == ""


def test_collect_and_write_persists_function_events_and_summary(monkeypatch, tmp_path):
    tracer = _reload_tracer(monkeypatch, tmp_path)
    live_file = tmp_path / "live_events.jsonl"
    live_file.write_text(
        "\n".join(
            [
                json.dumps({
                    "node_id": "deterministic_scan",
                    "stage_id": "deterministic_scan",
                    "outputs": {"candidate_count": 4},
                }),
                json.dumps({
                    "type": "fn_call",
                    "module": "modules.paper_analysis.pipeline",
                    "function": "_run_detail_extraction",
                    "pmid": "123",
                    "stage_id": "detail_extraction",
                }),
                json.dumps({
                    "type": "fn_return",
                    "module": "modules.paper_analysis.pipeline",
                    "function": "_run_detail_extraction",
                    "pmid": "123",
                    "stage_id": "detail_extraction",
                }),
                json.dumps({
                    "type": "fn_call",
                    "module": "modules.paper_analysis.pipeline",
                    "function": "_run_detail_extraction",
                    "pmid": "999",
                    "stage_id": "detail_extraction",
                }),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    trace_path = tracer.collect_and_write("123", tmp_path / "trace_123.json")

    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    fn_path = tmp_path / "trace_123_functions.jsonl"
    assert payload["function_event_count"] == 2
    assert payload["function_trace_path"] == str(fn_path)
    assert payload["function_counts_by_stage"]["detail_extraction"] == 2
    assert payload["function_counts_by_name"]["modules.paper_analysis.pipeline._run_detail_extraction"] == 2
    assert [event["type"] for event in _jsonl(fn_path)] == ["fn_call", "fn_return"]


def test_configure_trace_env_creates_cli_live_file(monkeypatch, tmp_path):
    from run_pipeline import _configure_trace_env

    for name in ("TRACE_PMID", "TRACE_OUT_DIR", "TRACE_LIVE_FILE", "TRACE_FUNCTIONS"):
        monkeypatch.delenv(name, raising=False)

    args = SimpleNamespace(
        trace_pmid="41017238",
        trace_functions=True,
        output_dir=str(tmp_path),
    )

    _configure_trace_env(args)

    assert (tmp_path / "live_events.jsonl").exists()
    assert (tmp_path / "live_events.jsonl").read_text(encoding="utf-8") == ""
    assert os.environ["TRACE_OUT_DIR"] == str(tmp_path / ".trace_partials")
    assert os.environ["TRACE_LIVE_FILE"] == str(tmp_path / "live_events.jsonl")


def test_function_trace_events_include_stage_id(monkeypatch, tmp_path):
    tracer = _reload_tracer(monkeypatch, tmp_path)

    from modules.abstract_screener import has_genetic_content

    tracer.install_function_tracer(max_events=50)
    try:
        with tracer.paper("123"):
            with tracer.stage("abstract_screening"):
                has_genetic_content("BRCA1 and TP53 mutations were found.", "Genetics")
    finally:
        tracer.uninstall_function_tracer()

    events = _jsonl(tmp_path / "live_events.jsonl")
    calls = [
        event
        for event in events
        if event.get("type") == "fn_call" and event.get("function") == "has_genetic_content"
    ]
    assert calls
    assert calls[0]["stage_id"] == "abstract_screening"
    assert calls[0]["pmid"] == "123"
