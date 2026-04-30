"""
Fixture-backed pipeline output contract tests.

These tests do not patch production modules or replace runtime boundaries. They
exercise the output writer and deterministic Stage 5 helpers with representative
records shaped like orchestrator output.
"""

import os
import re

import pandas as pd


USER_COLUMNS = {
    "Disease Association": "The disease or medical condition associated with this gene/variant",
    "Key Finding": "Main research finding about this gene from the paper",
    "Statistical Evidence": "P-values, odds ratios, or other statistical measures mentioned",
}

FIXTURE_ROWS = [
    {
        "Gene/Group": "BRCA1",
        "Variant Name": "p.Glu1915Ter",
        "PMID": "11111111",
        "Study Title": "BRCA1 and BRCA2 breast cancer mutation analysis",
        "Authors": "Smith J; Doe A",
        "Publication Year": "2022",
        "Journal Name": "Genetics",
        "Citations": 150,
        "Disease Association": "Breast cancer",
        "Disease Association Citation": "BRCA1 p.Glu1915Ter was associated with breast cancer.",
        "Key Finding": "BRCA1 truncating variant association",
        "Key Finding Citation": "BRCA1 p.Glu1915Ter was associated with breast cancer.",
        "Statistical Evidence": "p<0.001",
        "Statistical Evidence Citation": "The variant association reached p<0.001.",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "",
    },
    {
        "Gene/Group": "BRCA2",
        "Variant Name": "c.5946delT",
        "PMID": "11111111",
        "Study Title": "BRCA1 and BRCA2 breast cancer mutation analysis",
        "Authors": "Smith J; Doe A",
        "Publication Year": "2022",
        "Journal Name": "Genetics",
        "Citations": 150,
        "Disease Association": "Breast cancer",
        "Disease Association Citation": "BRCA2 c.5946delT was associated with breast cancer.",
        "Key Finding": "BRCA2 frameshift variant association",
        "Key Finding Citation": "BRCA2 c.5946delT was associated with breast cancer.",
        "Statistical Evidence": "OR 2.3",
        "Statistical Evidence Citation": "The odds ratio was 2.3.",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "",
    },
    {
        "Gene/Group": "EGFR",
        "Variant Name": "L858R",
        "PMID": "22222222",
        "Study Title": "EGFR mutations in lung cancer",
        "Authors": "Chen L; Patel R",
        "Publication Year": "2021",
        "Journal Name": "Oncology Reports",
        "Citations": 90,
        "Disease Association": "Lung cancer",
        "Disease Association Citation": "EGFR L858R was reported in lung cancer samples.",
        "Key Finding": "EGFR activating mutation",
        "Key Finding Citation": "EGFR L858R was reported in lung cancer samples.",
        "Statistical Evidence": "",
        "Statistical Evidence Citation": "",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "",
    },
    {
        "Gene/Group": "TCF7L2",
        "Variant Name": "rs7903146",
        "PMID": "33333333",
        "Study Title": "TCF7L2 variants and type 2 diabetes",
        "Authors": "Garcia M; Nguyen P",
        "Publication Year": "2020",
        "Journal Name": "Diabetes Genetics",
        "Citations": 70,
        "Disease Association": "Type 2 diabetes",
        "Disease Association Citation": "TCF7L2 rs7903146 was associated with type 2 diabetes.",
        "Key Finding": "TCF7L2 diabetes risk variant",
        "Key Finding Citation": "TCF7L2 rs7903146 was associated with type 2 diabetes.",
        "Statistical Evidence": "p=1e-8",
        "Statistical Evidence Citation": "The association had p=1e-8.",
        "validation_confidence": 1.0,
        "Gene Source": "both",
        "Candidate Source": "deterministic_lexicon,pubtator",
        "context_modifications": "",
    },
]


def _write_fixture_output(tmp_path):
    from modules.pipeline_orchestrator import _write_split_output

    df = pd.DataFrame(FIXTURE_ROWS)
    primary_path, metadata_path, excel_path, json_path = _write_split_output(
        df=df,
        output_path=tmp_path / "fixture_results.csv",
        user_cols=list(USER_COLUMNS),
    )
    return {
        "local_path": primary_path,
        "metadata_path": metadata_path,
        "excel_path": excel_path,
        "json_path": json_path,
    }


def test_pipeline_fixture_produces_output_files(tmp_path):
    result = _write_fixture_output(tmp_path)
    assert os.path.exists(result["local_path"])
    assert os.path.exists(result["metadata_path"])
    assert result["excel_path"].endswith("fixture_results.xlsx")
    assert result["json_path"].endswith("fixture_results.json")


def test_output_is_valid_csv(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    assert len(df) == len(FIXTURE_ROWS)


def test_core_columns_present(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])

    for col in ["Gene", "Variant", "PMID", "Title", "Authors", "Year", "Journal", "Citations"]:
        assert col in df.columns, f"Missing core column: '{col}'"


def test_user_columns_present(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])

    for col_name in USER_COLUMNS:
        assert col_name in df.columns, f"Missing user column: '{col_name}'"


def test_pmids_in_output(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    assert set(df["PMID"].astype(str).unique()) == {"11111111", "22222222", "33333333"}


def test_gene_symbols_are_valid(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    gene_pattern = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")

    for gene in df["Gene"].dropna():
        assert gene_pattern.match(str(gene).strip())


def test_variant_format(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    combined_pattern = re.compile(
        "|".join([
            r"^c\.\d+",
            r"^p\.[A-Z]",
            r"^rs\d+",
            r"^[A-Z]\d+[A-Z]$",
            r"^[A-Z][a-z]{2}\d+[A-Z][a-z]{2}$",
            r".*del.*",
            r".*dup.*",
            r".*ins.*",
        ]),
        re.IGNORECASE,
    )

    for variant in df["Variant"].dropna():
        variant_text = str(variant).strip()
        if variant_text:
            assert combined_pattern.match(variant_text)


def test_expected_genes_found(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    assert {"BRCA1", "BRCA2", "EGFR", "TCF7L2"}.issubset(set(df["Gene"]))


def test_no_empty_titles(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    assert not (df["Title"].fillna("") == "").any()


def test_column_order(tmp_path):
    result = _write_fixture_output(tmp_path)
    df = pd.read_csv(result["local_path"])
    cols = list(df.columns)

    assert cols[0] == "Gene"
    pmid_idx = cols.index("PMID")
    for user_col in USER_COLUMNS:
        assert cols.index(user_col) < pmid_idx


def test_pmid_41017238_f12_regression():
    """Co-mentioned genes should retain co-mention metadata after backfill."""
    from modules.gemini_extractor import GeneInfoPipeline

    paper_text = (
        "Furthermore, ITPKC, CASP3, and FCGR2A contribute together to "
        "Kawasaki disease susceptibility."
    )
    pipeline = GeneInfoPipeline(
        paper_text=paper_text,
        abstract_text="",
        pubtator_genes=[],
        figure_inputs=[],
        client=object(),
    )
    rows = [
        {"gene_name": "ITPKC", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
        {"gene_name": "CASP3", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
        {"gene_name": "FCGR2A", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
    ]

    pipeline._backfill_sparse_row_evidence(
        rows, {"Key Finding": "primary finding about the gene"}
    )

    for row in rows:
        assert row["Key Finding"]
        assert row["evidence_backfilled"] is True

    n_gene_specific = sum(
        1 for row in rows if row.get("evidence_specificity") == "gene_specific"
    )
    assert n_gene_specific <= 1
    for row in rows:
        if row.get("evidence_specificity") == "co_mention":
            assert row.get("co_mentioned_genes")
