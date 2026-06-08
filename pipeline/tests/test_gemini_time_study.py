import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYZER_PATH = REPO_ROOT / "studies" / "gemini_time_of_day" / "analyze_results.py"
RUNNER_PATH = REPO_ROOT / "studies" / "gemini_time_of_day" / "run_study.py"
HOURLY_DRIVER_PATH = REPO_ROOT / "studies" / "gemini_time_of_day" / "run_hourly_study.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_analyzer_classifies_complete_quota_free_runs_as_usable():
    analyzer = _load_module(ANALYZER_PATH, "gemini_time_analyzer")
    manifests = []
    for idx, block in enumerate(["03:00", "09:00", "15:00", "21:00"], start=1):
        manifests.append(
            {
                "run_id": f"run_{idx}",
                "time_block": block,
                "repeat": 1,
                "runtime_seconds": 3600,
                "return_code": 0,
                "batch": {
                    "completed_papers": 10,
                    "total_papers": 10,
                    "quota_limited_rows": 0,
                    "quota_limited_papers": 0,
                    "quota_warning_count": 0,
                    "timeout_count": 0,
                    "gemini_api_calls": 20,
                    "output_rows": 40,
                },
                "per_paper": [],
            }
        )

    batch_rows, _, block_rows = analyzer.summarize(manifests)

    assert analyzer.classify(batch_rows, block_rows) == "usable"


def test_analyzer_marks_low_completion_as_not_usable():
    analyzer = _load_module(ANALYZER_PATH, "gemini_time_analyzer_low_completion")
    manifests = [
        {
            "run_id": "bad",
            "time_block": "09:00",
            "repeat": 1,
            "runtime_seconds": 1200,
            "return_code": 0,
            "batch": {
                "completed_papers": 5,
                "total_papers": 10,
                "quota_limited_rows": 12,
                "timeout_count": 1,
                "output_rows": 8,
            },
            "per_paper": [],
        }
    ]

    batch_rows, _, block_rows = analyzer.summarize(manifests)

    assert analyzer.classify(batch_rows, block_rows) == "not_usable"


def test_analyzer_requires_all_time_blocks_before_positive_verdict():
    analyzer = _load_module(ANALYZER_PATH, "gemini_time_analyzer_insufficient")
    manifests = [
        {
            "run_id": "hour23",
            "time_block": "evening",
            "repeat": 1,
            "runtime_seconds": 900,
            "return_code": 0,
            "batch": {
                "completed_papers": 10,
                "total_papers": 10,
                "quota_limited_rows": 0,
                "timeout_count": 0,
                "output_rows": 40,
            },
            "per_paper": [],
        }
    ]

    batch_rows, _, block_rows = analyzer.summarize(manifests)

    assert analyzer.classify(batch_rows, block_rows) == "insufficient_data"


def test_analyzer_excludes_unlocked_corpus_manifests(tmp_path):
    analyzer = _load_module(ANALYZER_PATH, "gemini_time_analyzer_corpus_lock")
    expected_pmids = [str(1000 + idx) for idx in range(10)]
    expected_fingerprint = analyzer.pmid_fingerprint(expected_pmids)
    old_dir = tmp_path / "runs" / "old"
    current_dir = tmp_path / "runs" / "current"
    old_dir.mkdir(parents=True)
    current_dir.mkdir(parents=True)
    old_manifest = {
        "run_id": "old",
        "time_block": "evening",
        "batch": {"completed_papers": 10, "total_papers": 10},
    }
    current_manifest = {
        "run_id": "current",
        "time_block": "morning",
        "corpus_fingerprint": expected_fingerprint,
        "batch": {"completed_papers": 10, "total_papers": 10},
    }
    (old_dir / "study_run.json").write_text(json.dumps(old_manifest), encoding="utf-8")
    (current_dir / "study_run.json").write_text(json.dumps(current_manifest), encoding="utf-8")

    manifests = analyzer.collect_manifests(
        tmp_path / "runs",
        expected_corpus_fingerprint=expected_fingerprint,
    )

    assert [manifest["run_id"] for manifest in manifests] == ["current"]


def test_runner_extracts_result_and_derives_paper_timing():
    runner = _load_module(RUNNER_PATH, "gemini_time_runner")
    events = [
        {
            "epoch": 100.0,
            "kind": "log",
            "payload": {
                "level": "info",
                "msg": "Analyzing paper 1/2: One",
                "detail": "PMID 111",
            },
        },
        {
            "epoch": 160.0,
            "kind": "log",
            "payload": {
                "level": "info",
                "msg": "Analyzing paper 2/2: Two",
                "detail": "PMID 222",
            },
        },
        {
            "epoch": 200.0,
            "kind": "result",
            "payload": {"local_path": "/tmp/results.csv"},
        },
    ]

    assert runner.extract_result(events) == {"local_path": "/tmp/results.csv"}
    assert runner.derive_paper_timings(events, ["111", "222"], 220.0) == {
        "111": 60.0,
        "222": 60.0,
    }


def test_runner_counts_recovered_model_unavailable_events(tmp_path):
    runner = _load_module(RUNNER_PATH, "gemini_time_runner_unavailable")
    result_csv = tmp_path / "results.csv"
    result_csv.write_text("Gene,PMID\nBRCA1,111\n", encoding="utf-8")
    debug_path = tmp_path / "debug.json"
    debug_path.write_text(
        json.dumps(
            {
                "pipeline_stats": {"gemini_api_calls": 3},
                "paper_debug": [{"pmid": "111", "status": "ok", "emitted_rows": 1}],
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "epoch": 100.0,
            "kind": "stdout",
            "payload": "ERROR:root:Error during extraction: 503 UNAVAILABLE",
        },
        {
            "epoch": 101.0,
            "kind": "log",
            "payload": {"msg": "Analyzing paper 1/1", "detail": "PMID 111"},
        },
        {
            "epoch": 150.0,
            "kind": "result",
            "payload": {"local_path": str(result_csv), "debug_path": str(debug_path)},
        },
    ]

    manifest = runner.summarize_run(
        run_id="hour00",
        planned_entry={"time_block": "night"},
        pmids=["111"],
        start_epoch=100.0,
        end_epoch=160.0,
        return_code=0,
        events=events,
        output_dir=tmp_path,
        corpus_fingerprint="fingerprint",
        timezone_name="Europe/Warsaw",
        quota_snapshot_path=None,
        usage_before=None,
        usage_after=None,
    )

    assert manifest["batch"]["gemini_error_count"] == 1
    assert manifest["batch"]["model_unavailable_count"] == 1


def test_runner_summarizes_exact_gemini_token_usage(tmp_path):
    runner = _load_module(RUNNER_PATH, "gemini_time_runner_tokens")
    result_csv = tmp_path / "results.csv"
    result_csv.write_text("Gene,PMID\nBRCA1,111\n", encoding="utf-8")
    debug_path = tmp_path / "debug.json"
    debug_path.write_text(
        json.dumps(
            {
                "pipeline_stats": {
                    "gemini_api_calls": 2,
                    "gemini_usage_metadata_calls": 2,
                    "gemini_prompt_tokens": 100,
                    "gemini_response_tokens": 20,
                    "gemini_total_tokens": 120,
                },
                "paper_debug": [
                    {
                        "pmid": "111",
                        "status": "ok",
                        "api_calls_this_paper": 2,
                        "gemini_usage_summary": {
                            "gemini_usage_metadata_calls": 2,
                            "gemini_prompt_tokens": 100,
                            "gemini_response_tokens": 20,
                            "gemini_total_tokens": 120,
                        },
                        "emitted_rows": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "epoch": 100.0,
            "kind": "log",
            "payload": {"msg": "Analyzing paper 1/1", "detail": "PMID 111"},
        },
        {
            "epoch": 150.0,
            "kind": "result",
            "payload": {"local_path": str(result_csv), "debug_path": str(debug_path)},
        },
    ]

    manifest = runner.summarize_run(
        run_id="hour00",
        planned_entry={"time_block": "night"},
        pmids=["111"],
        start_epoch=100.0,
        end_epoch=160.0,
        return_code=0,
        events=events,
        output_dir=tmp_path,
        corpus_fingerprint="fingerprint",
        timezone_name="Europe/Warsaw",
        quota_snapshot_path=None,
        usage_before=None,
        usage_after=None,
    )

    assert manifest["batch"]["gemini_prompt_tokens"] == 100
    assert manifest["batch"]["gemini_response_tokens"] == 20
    assert manifest["batch"]["gemini_total_tokens"] == 120
    assert manifest["per_paper"][0]["gemini_api_calls"] == 2
    assert manifest["per_paper"][0]["gemini_total_tokens"] == 120


def test_analyzer_computes_output_stability_jaccard(tmp_path):
    analyzer = _load_module(ANALYZER_PATH, "gemini_time_analyzer_stability")
    run1_csv = tmp_path / "run1.csv"
    run1_csv.write_text(
        "PMID,Gene,Variant\n111,BRCA1,c.1A>G\n111,TP53,\n",
        encoding="utf-8",
    )
    run2_csv = tmp_path / "run2.csv"
    run2_csv.write_text(
        "PMID,Gene,Variant\n111,BRCA1,c.1A>G\n111,EGFR,\n",
        encoding="utf-8",
    )
    manifests = [
        {
            "run_id": "hour00",
            "outputs": {"csv": str(run1_csv)},
            "per_paper": [
                {
                    "pmid": "111",
                    "emitted_rows": 2,
                    "strict_gate_drops": 1,
                    "citation_gate_drops": 0,
                }
            ],
        },
        {
            "run_id": "hour01",
            "outputs": {"csv": str(run2_csv)},
            "per_paper": [
                {
                    "pmid": "111",
                    "emitted_rows": 2,
                    "strict_gate_drops": 0,
                    "citation_gate_drops": 1,
                }
            ],
        },
    ]

    rows = analyzer.output_stability_rows(manifests)

    assert len(rows) == 1
    row = rows[0]
    assert row["pmid"] == "111"
    assert row["cv_emitted_rows"] == 0
    assert round(row["mean_gene_jaccard"], 3) == 0.333
    assert row["mean_gene_variant_jaccard"] == 1.0
    assert round(row["mean_validation_gate_drop_rate"], 3) == 0.333


def test_runner_refuses_unverified_full_corpus(tmp_path):
    runner = _load_module(RUNNER_PATH, "gemini_time_runner_unverified")
    corpus = {
        "verified": False,
        "pmids": [{"pmid": str(1000 + idx)} for idx in range(10)],
    }
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(json.dumps(corpus), encoding="utf-8")

    try:
        runner.load_pmids(corpus_path, allow_unverified=False)
    except SystemExit as exc:
        assert "not marked verified" in str(exc)
    else:
        raise AssertionError("unverified corpus should stop formal runs")


def test_runner_refuses_formal_run_before_scheduled_time():
    runner = _load_module(RUNNER_PATH, "gemini_time_runner_schedule_guard")
    planned = {
        "run_id": "hour00",
        "planned_date": "2026-06-09",
        "planned_local_time": "00:00",
    }

    try:
        runner.validate_schedule_time(
            planned,
            timezone_name="Europe/Warsaw",
            now=datetime(2026, 6, 8, 23, 59, tzinfo=ZoneInfo("Europe/Warsaw")),
        )
    except SystemExit as exc:
        assert "Refusing to start before scheduled local time" in str(exc)
    else:
        raise AssertionError("formal run should stop before planned local time")


def test_runner_allows_formal_run_at_scheduled_time():
    runner = _load_module(RUNNER_PATH, "gemini_time_runner_schedule_allow")
    planned = {
        "run_id": "hour00",
        "planned_date": "2026-06-09",
        "planned_local_time": "00:00",
    }

    runner.validate_schedule_time(
        planned,
        timezone_name="Europe/Warsaw",
        now=datetime(2026, 6, 9, 0, 0, tzinfo=ZoneInfo("Europe/Warsaw")),
    )


def test_formal_schedule_uses_hourly_runs_with_500_rpd_headroom():
    schedule = json.loads(
        (REPO_ROOT / "studies" / "gemini_time_of_day" / "schedule.json").read_text(
            encoding="utf-8"
        )
    )
    runs = schedule["runs"]
    blocks = {}
    for run in runs:
        blocks[run["time_block"]] = blocks.get(run["time_block"], 0) + 1

    assert schedule["quota_policy"]["active_model"] == "gemini-3.1-flash-lite"
    assert schedule["quota_policy"]["active_daily_limit_requests"] == 500
    assert schedule["quota_policy"]["estimated_max_requests_per_quota_window"] <= 500
    assert len(runs) == 24
    assert blocks == {"night": 6, "morning": 6, "afternoon": 6, "evening": 6}


def test_hourly_driver_generates_24_hour_balanced_schedule():
    driver = _load_module(HOURLY_DRIVER_PATH, "gemini_hourly_driver")
    start_at = datetime(2026, 6, 9, 0, 0, tzinfo=ZoneInfo("Europe/Warsaw"))
    schedule = driver.generate_schedule(start_at, 24, "Europe/Warsaw")
    runs = schedule["runs"]
    blocks = {}
    for run in runs:
        blocks[run["time_block"]] = blocks.get(run["time_block"], 0) + 1

    assert len(runs) == 24
    assert runs[0]["run_id"] == "hour00"
    assert runs[-1]["run_id"] == "hour23"
    assert blocks == {"night": 6, "morning": 6, "afternoon": 6, "evening": 6}
    assert runs[8]["quota_window_start_date"] == "2026-06-08"
    assert runs[9]["quota_window_start_date"] == "2026-06-09"
    assert schedule["quota_policy"]["estimated_requests_per_10_paper_batch"] == 22
    assert schedule["quota_policy"]["estimated_total_24_hour_requests"] == 528
    assert schedule["quota_policy"]["max_requests_per_quota_window"] == 480
