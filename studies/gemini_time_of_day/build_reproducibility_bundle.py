#!/usr/bin/env python3
"""Build a sanitized, checksum-addressed bundle for the completed WSL study."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = Path(__file__).resolve().parent
DEFAULT_SESSION = STUDY_DIR / "runs/session_20260609_0100_scheduler"
DEFAULT_OUTPUT = STUDY_DIR / "reproducibility/v1.0.2"
DEFAULT_NUMERIC_REPORTS = STUDY_DIR / "reports"

REPORT_FILES = (
    "batch_metrics.csv",
    "paper_metrics.csv",
    "time_block_summary.csv",
    "descriptive_summary.csv",
    "failure_events.csv",
    "stability_metrics.csv",
    "gate_events.csv",
    "gate_by_run.csv",
    "gate_by_pmid.csv",
    "gate_summary.csv",
)
NUMERIC_FILES = (
    "numeric_preservation_summary.csv",
    "numeric_preservation_by_pmid.csv",
    "numeric_preservation_by_run.csv",
)
PLOT_FILES = (
    "batch_runtime_by_hour.svg",
    "gemini_calls_by_hour.svg",
    "gemini_tokens_by_hour.svg",
    "output_rows_by_hour.svg",
    "failure_matrix.svg",
    "runtime_by_time_block.svg",
    "per_pmid_output_rows_heatmap.svg",
)
SENSITIVE_COLUMN_FRAGMENTS = (
    "api_key",
    "email",
    "secret",
    "password",
    "artifact_path",
    "manifest_path",
    "output_path",
    "detail_extraction_error",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_sensitive_column(name: str) -> bool:
    lowered = name.lower()
    return any(fragment in lowered for fragment in SENSITIVE_COLUMN_FRAGMENTS)


def sanitize_csv(source: Path, destination: Path) -> None:
    with source.open("r", encoding="utf-8", newline="") as input_fh:
        reader = csv.DictReader(input_fh)
        fieldnames = [
            name
            for name in (reader.fieldnames or [])
            if not is_sensitive_column(name)
        ]
        rows = [
            {name: row.get(name, "") for name in fieldnames}
            for row in reader
        ]
    with destination.open("w", encoding="utf-8", newline="") as output_fh:
        writer = csv.DictWriter(output_fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sanitized_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version"),
        "timezone": payload.get("timezone"),
        "cadence_minutes": payload.get("cadence_minutes"),
        "quota_policy": payload.get("quota_policy"),
        "policy": payload.get("policy"),
        "runs": payload.get("runs"),
    }


def sanitized_corpus(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version"),
        "verified": payload.get("verified"),
        "selection_policy": payload.get("selection_policy"),
        "pmids": [
            {
                "pmid": row.get("pmid"),
                "size_class": row.get("size_class"),
                "source_hint": row.get("source_hint"),
            }
            for row in payload.get("pmids") or []
        ],
    }


def build_provenance(
    manifests: list[dict[str, Any]],
    *,
    release_version: str,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    commits = sorted(
        {
            str(manifest.get("git_commit") or "")
            for manifest in manifests
            if manifest.get("git_commit")
        }
    )
    fingerprints = sorted(
        {
            str(manifest.get("corpus_fingerprint") or "")
            for manifest in manifests
            if manifest.get("corpus_fingerprint")
        }
    )
    models = sorted(
        {
            str((manifest.get("settings") or {}).get("GEMINI_GENE_EXTRACTION_MODEL") or "")
            for manifest in manifests
            if (manifest.get("settings") or {}).get("GEMINI_GENE_EXTRACTION_MODEL")
        }
    )
    dirty_values = sorted({bool(manifest.get("git_dirty")) for manifest in manifests})
    planned_dates = sorted(
        {
            str(manifest.get("planned_date") or "")
            for manifest in manifests
            if manifest.get("planned_date")
        }
    )
    return {
        "schema_version": "researchshop_wsl_reproducibility_bundle_v1",
        "release_version": release_version,
        "release_source_ref": release_version,
        "execution_environment": "Windows laptop; WSL Ubuntu",
        "timezone": schedule.get("timezone"),
        "planned_dates": planned_dates,
        "attempted_slots": len(manifests),
        "study_execution_commits": commits,
        "git_dirty_values_recorded": dirty_values,
        "git_dirty_caveat": (
            "The WSL manifests contain both clean and dirty git states. "
            "The recorded commit identifies the base source, but later-run "
            "uncommitted changes cannot be reconstructed from the bundle."
        ),
        "models": models,
        "corpus_fingerprints": fingerprints,
        "study_type": "operational reliability and output-stability study",
        "accuracy_scope": (
            "No expert-labelled reference set was used. The bundle does not "
            "estimate biological precision, recall, F1, or clinical validity."
        ),
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_checksums(output_dir: Path) -> None:
    files = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "CHECKSUMS.sha256"
    )
    lines = [
        f"{sha256(path)}  {path.relative_to(output_dir).as_posix()}"
        for path in files
    ]
    (output_dir / "CHECKSUMS.sha256").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def assert_bundle_is_sanitized(output_dir: Path) -> None:
    forbidden = (
        "AIza",
        "AQ.",
        "@gmail.com",
        "/Users/",
        "/home/student/",
        "GEMINI_API_KEY",
        "ENTREZ_EMAIL",
    )
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".csv", ".json", ".md", ".sha256", ".svg"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in forbidden:
            if marker in text:
                raise ValueError(f"Forbidden marker {marker!r} found in {path}")


def write_readme(path: Path, release_version: str) -> None:
    path.write_text(
        f"""# ResearchShop Gemini Free-Tier Reproducibility Bundle

Release: `{release_version}`

This sanitized bundle contains aggregate results from the completed 24-hour
Windows/WSL operational study. The same locked 10-PMID corpus was processed
once per Warsaw-local hour with `gemini-3.1-flash-lite`.

## Statistical Units

- Candidate dispositions describe candidate records evaluated before row
  construction.
- Row dispositions describe final export decisions. Their denominator is
  independent of the candidate-record denominator.
- Recovered API events are log events matched by the study harness; they are
  not guaranteed to be unique failed HTTP requests.
- Stability statistics compare repeated outputs from the same PMIDs.

## Exclusions

The bundle excludes API keys, email addresses, personal filesystem paths,
downloaded article text, citation-bearing result rows, workbooks, and raw
debug artifacts. It contains no expert annotation and does not estimate
biological precision, recall, F1, or clinical validity.

## Regeneration

The aggregate reports were generated with:

```bash
python studies/gemini_time_of_day/analyze_results.py \\
  --run-root studies/gemini_time_of_day/runs/session_20260609_0100_scheduler \\
  --report-dir studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/reports
```

`CHECKSUMS.sha256` verifies every included file.
""",
        encoding="utf-8",
    )


def build_bundle(
    *,
    session_dir: Path,
    output_dir: Path,
    numeric_report_dir: Path,
    release_version: str,
) -> None:
    report_dir = session_dir / "reports"
    manifest_paths = sorted(session_dir.glob("hour*/study_run.json"))
    if not manifest_paths:
        raise FileNotFoundError(f"No study manifests found under {session_dir}")
    manifests = [load_json(path) for path in manifest_paths]
    schedule = load_json(session_dir / "schedule.json")
    corpus = load_json(STUDY_DIR / "corpus.json")

    output_dir.mkdir(parents=True, exist_ok=True)
    reports_out = output_dir / "reports"
    plots_out = output_dir / "plots"
    reports_out.mkdir(exist_ok=True)
    plots_out.mkdir(exist_ok=True)

    for filename in REPORT_FILES:
        source = report_dir / filename
        if not source.exists():
            raise FileNotFoundError(f"Missing required report: {source}")
        sanitize_csv(source, reports_out / filename)

    for filename in NUMERIC_FILES:
        source = numeric_report_dir / filename
        if source.exists():
            sanitize_csv(source, reports_out / filename)

    for filename in PLOT_FILES:
        source = report_dir / "plots" / filename
        if source.exists():
            shutil.copyfile(source, plots_out / filename)
    numeric_heatmap = numeric_report_dir / "numeric_preservation_heatmap.svg"
    if numeric_heatmap.exists():
        shutil.copyfile(numeric_heatmap, plots_out / numeric_heatmap.name)

    write_json(output_dir / "schedule.json", sanitized_schedule(schedule))
    write_json(output_dir / "corpus.json", sanitized_corpus(corpus))
    write_json(
        output_dir / "provenance.json",
        build_provenance(
            manifests,
            release_version=release_version,
            schedule=schedule,
        ),
    )
    write_readme(output_dir / "README.md", release_version)
    write_checksums(output_dir)
    assert_bundle_is_sanitized(output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--numeric-report-dir",
        type=Path,
        default=DEFAULT_NUMERIC_REPORTS,
    )
    parser.add_argument("--release-version", default="v1.0.2")
    args = parser.parse_args()

    build_bundle(
        session_dir=args.session_dir,
        output_dir=args.output_dir,
        numeric_report_dir=args.numeric_report_dir,
        release_version=args.release_version,
    )
    print(f"Wrote sanitized bundle: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
