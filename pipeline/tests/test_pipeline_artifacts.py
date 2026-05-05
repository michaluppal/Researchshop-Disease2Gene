"""Compatibility tests for run-level debug and candidate audit artifacts."""

import json

import pandas as pd

from modules.pipeline_artifacts import RunArtifactWriter


def _deterministic_factory(tmp_path):
    counters = {}

    def create_filepath(prefix, extension):
        counters[prefix] = counters.get(prefix, 0) + 1
        return str(tmp_path / f"{prefix}_{counters[prefix]:02d}.{extension}")

    return create_filepath


def test_drop_debug_writer_preserves_payload_shape(tmp_path):
    logs = []
    writer = RunArtifactWriter(
        create_filepath=_deterministic_factory(tmp_path),
        emit_log=lambda level, msg, detail=None: logs.append((level, msg, detail)),
        clock=lambda: 123.5,
    )

    path = writer.write_drop_debug_artifact(
        status="completed",
        query="BRCA1",
        specific_pmids=["1"],
        specific_authors=["Smith"],
        top_n_cited=5,
        output_csv_path="/tmp/final.csv",
        paper_debug_artifacts=[{"pmid": "1", "status": "ok"}],
        pipeline_stats={"genes_extracted": 1, "strict_gate_drops": []},
        forensic_screening=[{"pmid": "1", "score": 12}],
        fetch_report=[{"pmid": "1", "method": "pmc"}],
    )

    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload == {
        "status": "completed",
        "generated_at_epoch": 123.5,
        "query": "BRCA1",
        "specific_pmids": ["1"],
        "specific_authors": ["Smith"],
        "top_n_cited": 5,
        "output_csv_path": "/tmp/final.csv",
        "paper_debug": [{"pmid": "1", "status": "ok"}],
        "pipeline_stats": {"genes_extracted": 1, "strict_gate_drops": []},
        "screening_decisions": [{"pmid": "1", "score": 12}],
        "fetch_outcomes": [{"pmid": "1", "method": "pmc"}],
    }
    assert logs == [("info", "Saved drop-debug artifact", path)]


def test_candidate_audit_writer_uses_emitted_rows_for_final_associations(tmp_path):
    logs = []
    writer = RunArtifactWriter(
        create_filepath=_deterministic_factory(tmp_path),
        emit_log=lambda level, msg, detail=None: logs.append((level, msg, detail)),
        clock=lambda: 456.0,
    )
    all_results_df = pd.DataFrame(
        [
            {
                "PMID": "1",
                "Gene/Group": "CASP3",
                "Variant Name": "",
                "Association Type": "animal_model_gene",
                "Association Group": "Animal Model Signal",
            },
            {
                "PMID": "1",
                "Gene/Group": "ITPKC",
                "Variant Name": "",
                "Association Type": "susceptibility_gene",
                "Association Group": "Primary Genetic Association",
            },
        ]
    )
    stale_debug = [
        {
            "pmid": "1",
            "status": "ok",
            "candidate_count": 2,
            "candidates": [{"association_group": "Review Needed"}],
            "final_associations": [{"gene": "OLD", "association_group": "Review Needed"}],
            "emitted_rows": 99,
        }
    ]

    path = writer.write_candidate_audit_artifact(
        all_results_df=all_results_df,
        paper_debug_artifacts=stale_debug,
        output_csv_path="/tmp/final.csv",
    )

    payload = json.loads(open(path, encoding="utf-8").read())
    assert payload["schema_version"] == "candidate_audit_v1"
    assert payload["generated_at_epoch"] == 456.0
    assert payload["summary"]["total_emitted_rows"] == 2
    assert payload["summary"]["association_group_counts"] == {
        "Animal Model Signal": 1,
        "Primary Genetic Association": 1,
    }
    paper = payload["papers"][0]
    assert paper["emitted_rows"] == 2
    assert paper["final_associations"] == [
        {
            "gene": "CASP3",
            "variant": "",
            "association_type": "animal_model_gene",
            "association_group": "Animal Model Signal",
        },
        {
            "gene": "ITPKC",
            "variant": "",
            "association_type": "susceptibility_gene",
            "association_group": "Primary Genetic Association",
        },
    ]
    assert logs == [("info", "Saved candidate audit artifact", path)]
