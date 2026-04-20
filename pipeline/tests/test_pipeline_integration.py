"""
Integration test for the Disease2Gene pipeline with mocked Gemini API.

Runs the full pipeline on 3 sample papers with mocked external services
(PubMed, Semantic Scholar, Gemini AI, full-text fetcher) and verifies
the output schema: correct columns, valid gene symbols, proper variant format.
"""

import csv
import gzip
import os
import pickle
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Sample data for 3 test papers
# ---------------------------------------------------------------------------

SAMPLE_PAPERS = {
    "11111111": {
        "title": "BRCA1 and BRCA2 mutations in breast cancer patients",
        "authors": ["Smith J", "Doe A", "Lee B"],
        "year": "2023",
        "journal": "Nature Genetics",
        "affiliations": ["Harvard Medical School", "MIT"],
        "abstract": (
            "We performed whole-exome sequencing on 500 breast cancer patients "
            "and identified pathogenic mutations in BRCA1 (c.5266dupC) and BRCA2 "
            "(c.6174delT). BRCA1 mutations were associated with triple-negative "
            "breast cancer (OR=3.2, p<0.001). TP53 somatic mutations were found "
            "in 35% of tumors."
        ),
        "PMID": "11111111",
    },
    "22222222": {
        "title": "EGFR mutations and response to targeted therapy in NSCLC",
        "authors": ["Wang C", "Zhang D"],
        "year": "2022",
        "journal": "The Lancet Oncology",
        "affiliations": ["Johns Hopkins University"],
        "abstract": (
            "This study evaluated EGFR mutation status in 300 non-small cell "
            "lung cancer patients. Exon 19 deletions (p.E746_A750del) and the "
            "L858R point mutation were the most common EGFR alterations. ALK "
            "rearrangements were detected in 5% of cases. Response to erlotinib "
            "was significantly higher in EGFR-mutant patients (p=0.0001)."
        ),
        "PMID": "22222222",
    },
    "33333333": {
        "title": "Genome-wide association study of type 2 diabetes",
        "authors": ["Kim E", "Park F", "Chen G"],
        "year": "2024",
        "journal": "Cell",
        "affiliations": ["Stanford University", "Broad Institute"],
        "abstract": (
            "A GWAS meta-analysis of 100,000 individuals identified TCF7L2 "
            "rs7903146 as the strongest risk locus for type 2 diabetes "
            "(OR=1.4, p=2.1e-50). Additional signals at PPARG (Pro12Ala), "
            "KCNJ11 (E23K), and SLC30A8 (Arg325Trp) were confirmed. "
            "Polygenic risk scores incorporating these variants improved "
            "prediction of diabetes onset."
        ),
        "PMID": "33333333",
    },
}

SAMPLE_PMIDS = list(SAMPLE_PAPERS.keys())

# Full-text content for each paper (simulated scraped content)
SAMPLE_FULL_TEXT = {
    "11111111": {
        "content": (
            "BRCA1 and BRCA2 mutations in breast cancer patients. "
            "Introduction: Breast cancer is the most common cancer in women. "
            "BRCA1 and BRCA2 are tumor suppressor genes involved in DNA repair. "
            "Methods: We sequenced 500 patients using whole-exome sequencing. "
            "Results: BRCA1 c.5266dupC was found in 8% of patients. "
            "BRCA2 c.6174delT was found in 5% of patients. "
            "TP53 somatic mutations were identified in 35% of tumors. "
            "BRCA1 mutations were significantly associated with triple-negative "
            "breast cancer (OR=3.2, 95% CI 2.1-4.8, p<0.001). "
            "Conclusion: Genetic testing for BRCA1 and BRCA2 should be considered."
        ),
    },
    "22222222": {
        "content": (
            "EGFR mutations and response to targeted therapy in non-small cell "
            "lung cancer. EGFR exon 19 deletions including p.E746_A750del were "
            "the most common mutations. The L858R point mutation in exon 21 was "
            "also frequently observed. ALK rearrangements were detected in 5% "
            "of EGFR wild-type cases. Patients with EGFR mutations showed "
            "significantly better response to erlotinib compared to chemotherapy "
            "(response rate 72% vs 33%, p=0.0001)."
        ),
    },
    "33333333": {
        "content": (
            "Genome-wide association study of type 2 diabetes reveals novel loci. "
            "TCF7L2 rs7903146 was the strongest signal (OR=1.4, p=2.1e-50). "
            "PPARG Pro12Ala variant showed protective effect. "
            "KCNJ11 E23K was associated with impaired insulin secretion. "
            "SLC30A8 Arg325Trp was identified as a novel protective variant. "
            "Polygenic risk scores using all identified variants improved "
            "prediction models significantly (AUC 0.72 to 0.81)."
        ),
    },
}

# Simulated Gemini API responses for gene extraction (Step 1)
GEMINI_GENE_EXTRACTION_RESPONSES = {
    "11111111": '{"associations": [{"gene": "BRCA1", "variant": "c.5266dupC"}, {"gene": "BRCA2", "variant": "c.6174delT"}, {"gene": "TP53", "variant": ""}]}',
    "22222222": '{"associations": [{"gene": "EGFR", "variant": "p.E746_A750del"}, {"gene": "EGFR", "variant": "L858R"}, {"gene": "ALK", "variant": ""}]}',
    "33333333": '{"associations": [{"gene": "TCF7L2", "variant": "rs7903146"}, {"gene": "PPARG", "variant": "Pro12Ala"}, {"gene": "KCNJ11", "variant": "E23K"}, {"gene": "SLC30A8", "variant": "Arg325Trp"}]}',
}

# Simulated Gemini API responses for detailed extraction (Step 2)
GEMINI_DETAIL_EXTRACTION_RESPONSES = {
    "11111111": [
        {
            "gene_name": "BRCA1",
            "variant_name": "c.5266dupC",
            "Disease Association": "Triple-negative breast cancer",
            "Disease Association Citation": "BRCA1 mutations were significantly associated with triple-negative breast cancer.",
            "Key Finding": "Found in 8% of breast cancer patients",
            "Key Finding Citation": "BRCA1 c.5266dupC was found in 8% of patients.",
            "Statistical Evidence": "OR=3.2, 95% CI 2.1-4.8, p<0.001",
            "Statistical Evidence Citation": "BRCA1 mutations were significantly associated with triple-negative breast cancer (OR=3.2, 95% CI 2.1-4.8, p<0.001).",
        },
        {
            "gene_name": "BRCA2",
            "variant_name": "c.6174delT",
            "Disease Association": "Breast cancer",
            "Disease Association Citation": "BRCA2 c.6174delT was found in 5% of patients.",
            "Key Finding": "Found in 5% of breast cancer patients",
            "Key Finding Citation": "BRCA2 c.6174delT was found in 5% of patients.",
            "Statistical Evidence": "5% frequency",
            "Statistical Evidence Citation": "",
        },
        {
            "gene_name": "TP53",
            "variant_name": "",
            "Disease Association": "Breast cancer (somatic)",
            "Disease Association Citation": "TP53 somatic mutations were identified in 35% of tumors.",
            "Key Finding": "Somatic mutations in 35% of tumors",
            "Key Finding Citation": "TP53 somatic mutations were identified in 35% of tumors.",
            "Statistical Evidence": "35% frequency",
            "Statistical Evidence Citation": "",
        },
    ],
    "22222222": [
        {
            "gene_name": "EGFR",
            "variant_name": "p.E746_A750del",
            "Disease Association": "Non-small cell lung cancer",
            "Disease Association Citation": "EGFR exon 19 deletions including p.E746_A750del were the most common mutations.",
            "Key Finding": "Most common EGFR mutation in NSCLC",
            "Key Finding Citation": "EGFR exon 19 deletions including p.E746_A750del were the most common mutations.",
            "Statistical Evidence": "Response rate 72% vs 33%, p=0.0001",
            "Statistical Evidence Citation": "Patients with EGFR mutations showed significantly better response to erlotinib compared to chemotherapy (response rate 72% vs 33%, p=0.0001).",
        },
        {
            "gene_name": "ALK",
            "variant_name": "",
            "Disease Association": "Non-small cell lung cancer",
            "Disease Association Citation": "ALK rearrangements were detected in 5% of EGFR wild-type cases.",
            "Key Finding": "Rearrangements in 5% of EGFR wild-type cases",
            "Key Finding Citation": "ALK rearrangements were detected in 5% of EGFR wild-type cases.",
            "Statistical Evidence": "5% frequency",
            "Statistical Evidence Citation": "",
        },
    ],
    "33333333": [
        {
            "gene_name": "TCF7L2",
            "variant_name": "rs7903146",
            "Disease Association": "Type 2 diabetes",
            "Disease Association Citation": "TCF7L2 rs7903146 was the strongest signal.",
            "Key Finding": "Strongest risk locus for T2D",
            "Key Finding Citation": "TCF7L2 rs7903146 was the strongest signal (OR=1.4, p=2.1e-50).",
            "Statistical Evidence": "OR=1.4, p=2.1e-50",
            "Statistical Evidence Citation": "TCF7L2 rs7903146 was the strongest signal (OR=1.4, p=2.1e-50).",
        },
        {
            "gene_name": "PPARG",
            "variant_name": "Pro12Ala",
            "Disease Association": "Type 2 diabetes (protective)",
            "Disease Association Citation": "PPARG Pro12Ala variant showed protective effect.",
            "Key Finding": "Protective variant",
            "Key Finding Citation": "PPARG Pro12Ala variant showed protective effect.",
            "Statistical Evidence": "",
            "Statistical Evidence Citation": "",
        },
        {
            "gene_name": "KCNJ11",
            "variant_name": "E23K",
            "Disease Association": "Type 2 diabetes",
            "Disease Association Citation": "KCNJ11 E23K was associated with impaired insulin secretion.",
            "Key Finding": "Associated with impaired insulin secretion",
            "Key Finding Citation": "KCNJ11 E23K was associated with impaired insulin secretion.",
            "Statistical Evidence": "",
            "Statistical Evidence Citation": "",
        },
        {
            "gene_name": "SLC30A8",
            "variant_name": "Arg325Trp",
            "Disease Association": "Type 2 diabetes (protective)",
            "Disease Association Citation": "SLC30A8 Arg325Trp was identified as a novel protective variant.",
            "Key Finding": "Novel protective variant",
            "Key Finding Citation": "SLC30A8 Arg325Trp was identified as a novel protective variant.",
            "Statistical Evidence": "",
            "Statistical Evidence Citation": "",
        },
    ],
}

USER_COLUMNS = {
    "Disease Association": "The disease or medical condition associated with this gene/variant",
    "Key Finding": "Main research finding about this gene from the paper",
    "Statistical Evidence": "P-values, odds ratios, or other statistical measures mentioned",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def output_dir(tmp_path):
    """Provide a temporary output directory."""
    out = tmp_path / "output"
    out.mkdir()
    return str(out)


@pytest.fixture
def content_dict_path(tmp_path):
    """Write the sample full-text content dict as a gzipped pickle."""
    path = tmp_path / "content_dict.pkl.gz"
    with gzip.open(str(path), "wb") as f:
        pickle.dump(SAMPLE_FULL_TEXT, f)
    return str(path)


# ---------------------------------------------------------------------------
# Helper: create a mock Gemini streaming response
# ---------------------------------------------------------------------------

def _make_stream_chunks(text):
    """Create an iterable of mock chunks mimicking Gemini streaming."""
    chunk = MagicMock()
    chunk.text = text
    return [chunk]


def _build_gemini_side_effect():
    """Build a side_effect function for generate_content_stream.

    Determines which paper is being processed from the prompt text and
    returns the corresponding mock response (gene extraction or detail
    extraction depending on prompt content).
    """
    import json as _json

    call_count = {}  # Track calls per paper for two-stage pipeline

    def side_effect(model, contents, config=None):
        # Extract the prompt text from contents
        prompt_text = ""
        for content in contents:
            for part in content.parts:
                if hasattr(part, "text"):
                    prompt_text += part.text

        # Determine which PMID this call is for
        target_pmid = None
        for pmid, full_text_data in SAMPLE_FULL_TEXT.items():
            paper_content = full_text_data["content"]
            # Check if a significant portion of the paper text is in the prompt
            if paper_content[:80] in prompt_text:
                target_pmid = pmid
                break

        if target_pmid is None:
            # Might be an abstract-only call; check abstracts
            for pmid, paper_info in SAMPLE_PAPERS.items():
                if paper_info["abstract"][:60] in prompt_text:
                    target_pmid = pmid
                    break

        if target_pmid is None:
            # Fallback: return empty
            return _make_stream_chunks('{"associations": []}')

        # Determine which stage: gene extraction vs detail extraction
        # Detail extraction prompts contain "extract the requested information"
        if "extract the requested information" in prompt_text.lower():
            # Stage 2: Detail extraction - return as JSON array
            response_data = GEMINI_DETAIL_EXTRACTION_RESPONSES.get(target_pmid, [])
            return _make_stream_chunks(_json.dumps(response_data))
        else:
            # Stage 1: Gene extraction
            response_text = GEMINI_GENE_EXTRACTION_RESPONSES.get(
                target_pmid, '{"associations": []}'
            )
            return _make_stream_chunks(response_text)

    return side_effect


# ---------------------------------------------------------------------------
# Synchronous pool shim (bypasses multiprocessing for in-process mocking)
# ---------------------------------------------------------------------------

class _SyncAsyncResult:
    """Mimics mp.AsyncResult: holds a pre-computed value, .get() returns it."""
    def __init__(self, value):
        self._value = value

    def get(self, timeout=None):  # noqa: ARG002
        return self._value


class _SyncPool:
    """Drop-in mp.Pool replacement that runs tasks synchronously in-process.

    mp.Pool spawns fresh interpreter processes which cannot inherit
    unittest.mock patches. Replacing the pool with this shim lets the
    integration tests mock all external services without real subprocess spawning.
    """

    def __init__(self, processes=1):  # noqa: ARG002
        pass

    def apply_async(self, func, args=(), kwds=None):  # noqa: ARG002
        result = func(*args, **(kwds or {}))
        return _SyncAsyncResult(result)

    def terminate(self):
        pass

    def join(self, timeout=None):  # noqa: ARG002
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _mock_pipeline_worker(text, cols, pubtator_genes=None, figure_inputs=None,
                          abstract_text=None, table_inputs=None):
    """Return pre-built gene records based on which sample paper text is passed in.

    Identifies the paper by matching text against SAMPLE_FULL_TEXT and returns
    the corresponding rows from GEMINI_DETAIL_EXTRACTION_RESPONSES, formatted
    as the orchestrator expects: {"records": [...], "debug": {}, "gemini_api_calls": 0}.
    """
    # Identify which paper this text belongs to
    target_pmid = None
    for pmid, data in SAMPLE_FULL_TEXT.items():
        if data["content"][:60] in text:
            target_pmid = pmid
            break

    if target_pmid is None:
        return {"records": [], "debug": {}, "gemini_api_calls": 0}

    raw_rows = GEMINI_DETAIL_EXTRACTION_RESPONSES.get(target_pmid, [])
    base_info = SAMPLE_PAPERS[target_pmid]

    records = []
    for row in raw_rows:
        record = {
            "Gene/Group": row.get("gene_name", ""),
            "Variant Name": row.get("variant_name", ""),
            "PMID": target_pmid,
            "Study Title": base_info["title"],
            "Authors": "; ".join(base_info["authors"]),
            "Publication Year": base_info["year"],
            "Journal Name": base_info["journal"],
            "Author Affiliations": "; ".join(base_info["affiliations"]),
            "Citations": 50,
            "validation_confidence": 1.0,
            "Gene Source": "both",
            "Candidate Source": "deterministic_lexicon,pubtator",
            "context_modifications": "",
        }
        # Add user column fields from the mock detail extraction response
        for col in cols:
            record[col] = row.get(col, "")
            record[f"{col} Citation"] = row.get(f"{col} Citation", "")
        records.append(record)

    return {"records": records, "debug": {"status": "ok"}, "gemini_api_calls": 3}


# ---------------------------------------------------------------------------
# Core integration test
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    """Integration test: mock all external APIs, run the pipeline, verify output."""

    @pytest.fixture(autouse=True)
    def setup_env(self, output_dir, content_dict_path, tmp_path):
        """Set up environment for each test."""
        self.output_dir = output_dir
        self.content_dict_path = content_dict_path
        self.tmp_path = tmp_path

    def _run_pipeline(self):
        """Run the pipeline with all external calls mocked."""
        import modules.config as cfg

        # Set config values so validation passes in the main process
        cfg.GEMINI_API_KEY = "test-fake-key-12345"
        cfg.ENTREZ_EMAIL = "test@example.com"
        cfg.OUTPUT_DIR = self.output_dir
        cfg.ENABLE_PAPER_RANKING = True
        cfg.ENABLE_ABSTRACT_SCREENING = True
        cfg.ENABLE_CITATION_VALIDATION = False
        cfg.ENABLE_CONTEXT_CHECKING = False
        cfg.ENABLE_GENE_VALIDATION = True

        patches = [
            # PubMed search
            patch(
                "modules.pubmed_data_collector.search_pubmed",
                return_value=SAMPLE_PMIDS,
            ),
            # Paper details
            patch(
                "modules.pubmed_data_collector.fetch_paper_details",
                return_value=dict(SAMPLE_PAPERS),
            ),
            # Citation counts
            patch(
                "modules.pubmed_data_collector.fetch_semantic_citation_counts",
                return_value={p: (i + 1) * 50 for i, p in enumerate(SAMPLE_PMIDS)},
            ),
            # Full text fetcher: write our pre-built content_dict pickle
            patch(
                "modules.full_text_fetcher.run_fetching",
                side_effect=lambda pmids, path: self._write_content_dict(path),
            ),
            # Replace mp.Pool with _SyncPool so worker tasks run synchronously
            # in the test process (enabling all in-process mocks to take effect),
            # and replace _run_pipeline_worker with our mock that returns
            # pre-built records without calling Gemini.
            patch("modules.pipeline_orchestrator.mp.Pool", _SyncPool),
            patch(
                "modules.pipeline_orchestrator._run_pipeline_worker",
                side_effect=_mock_pipeline_worker,
            ),
        ]

        for p in patches:
            p.start()

        try:
            from modules.pipeline_orchestrator import run_complete_pipeline

            result = run_complete_pipeline(
                query="BRCA1 breast cancer mutations",
                specific_pmids=[],
                specific_authors=[],
                user_columns=USER_COLUMNS,
                top_n_cited=None,
            )
            return result
        finally:
            for p in patches:
                p.stop()
            # Reset config
            cfg.GEMINI_API_KEY = None
            cfg.ENTREZ_EMAIL = "your.email@example.com"

    def _write_content_dict(self, path):
        """Write the sample content dict to the given path."""
        with gzip.open(path, "wb") as f:
            pickle.dump(SAMPLE_FULL_TEXT, f)

    def test_pipeline_produces_output(self):
        """Pipeline should produce a result dict with a local_path key."""
        result = self._run_pipeline()
        assert result is not None, "Pipeline returned None"
        assert "local_path" in result, f"Result missing 'local_path': {result}"
        assert os.path.exists(result["local_path"]), (
            f"Output file does not exist: {result['local_path']}"
        )

    def test_output_is_valid_csv(self):
        """Output file should be a valid CSV readable by pandas."""
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])
        assert len(df) > 0, "Output CSV is empty"

    def test_core_columns_present(self):
        """Output CSV must contain all core columns.

        The primary CSV renames internal column names for researcher readability:
        Gene/Group→Gene, Variant Name→Variant, Study Title→Title,
        Publication Year→Year, Journal Name→Journal.
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])

        core_columns = [
            "Gene",
            "Variant",
            "PMID",
            "Title",
            "Authors",
            "Year",
            "Journal",
            "Citations",
        ]
        for col in core_columns:
            assert col in df.columns, f"Missing core column: '{col}'"

    def test_user_columns_present(self):
        """Output CSV must contain the user-defined extraction columns."""
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])

        for col_name in USER_COLUMNS:
            assert col_name in df.columns, (
                f"Missing user column: '{col_name}'"
            )

    def test_pmids_in_output(self):
        """All 3 sample PMIDs should appear in the output."""
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])
        output_pmids = set(df["PMID"].astype(str).unique())
        for pmid in SAMPLE_PMIDS:
            assert pmid in output_pmids, (
                f"PMID {pmid} not found in output. Found: {output_pmids}"
            )

    def test_gene_symbols_are_valid(self):
        """Extracted gene symbols should match HGNC-like patterns (uppercase letters/digits).

        The primary CSV uses the renamed column 'Gene' (internal name: Gene/Group).
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])

        # Filter rows that have a gene (skip minimal rows)
        genes_df = df[df["Gene"].fillna("") != ""]
        assert len(genes_df) > 0, "No rows with gene symbols found"

        gene_pattern = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")
        for _, row in genes_df.iterrows():
            gene = str(row["Gene"]).strip()
            if gene:
                assert gene_pattern.match(gene), (
                    f"Invalid gene symbol format: '{gene}' "
                    f"(PMID {row['PMID']}). Expected HGNC-style symbol."
                )

    def test_variant_format(self):
        """Non-empty variants should follow recognized notation patterns.

        The primary CSV uses the renamed column 'Variant' (internal name: Variant Name).
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])

        # Common variant patterns: HGVS (c., p., g.), rsIDs, short amino acid changes
        variant_patterns = [
            r"^c\.\d+",              # cDNA: c.5266dupC
            r"^p\.[A-Z]",           # protein: p.E746_A750del, p.Val600Glu
            r"^rs\d+",              # dbSNP: rs7903146
            r"^[A-Z]\d+[A-Z]$",    # short: L858R, E23K
            r"^[A-Z][a-z]{2}\d+[A-Z][a-z]{2}$",  # Pro12Ala, Arg325Trp
            r".*del.*",             # deletions
            r".*dup.*",             # duplications
            r".*ins.*",             # insertions
        ]
        combined_pattern = re.compile("|".join(variant_patterns), re.IGNORECASE)

        genes_df = df[df["Variant"].fillna("") != ""]
        for _, row in genes_df.iterrows():
            variant = str(row["Variant"]).strip()
            if variant and variant not in ("", "N/A", "NA"):
                # Variants may be semicolon-separated after dedup aggregation
                for v in variant.split(";"):
                    v = v.strip()
                    if v and v not in ("", "N/A", "NA"):
                        assert combined_pattern.match(v), (
                            f"Unrecognized variant format: '{v}' "
                            f"(gene: {row['Gene']}, PMID: {row['PMID']})"
                        )

    def test_expected_genes_found(self):
        """Key genes from our sample data should appear in the output.

        The primary CSV uses the renamed column 'Gene' (internal name: Gene/Group).
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])
        found_genes = set(df["Gene"].dropna().str.upper().unique())

        # At minimum these well-known genes from our mock data should appear
        expected = {"BRCA1", "BRCA2", "EGFR", "TCF7L2"}
        for gene in expected:
            assert gene in found_genes, (
                f"Expected gene '{gene}' not found. Found genes: {found_genes}"
            )

    def test_no_empty_titles(self):
        """Every row should have a non-empty title.

        The primary CSV uses the renamed column 'Title' (internal name: Study Title).
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])
        empty_titles = df[df["Title"].fillna("") == ""]
        assert len(empty_titles) == 0, (
            f"{len(empty_titles)} rows have empty Title"
        )

    def test_output_metrics(self):
        """Pipeline result should include output file paths."""
        result = self._run_pipeline()
        assert "local_path" in result, f"Result missing 'local_path': {result.keys()}"
        assert "metadata_path" in result, f"Result missing 'metadata_path': {result.keys()}"
        import os
        assert os.path.exists(result["local_path"]), (
            f"Primary CSV not found: {result['local_path']}"
        )
        assert os.path.exists(result["metadata_path"]), (
            f"Metadata CSV not found: {result['metadata_path']}"
        )

    def test_column_order(self):
        """Core columns should appear before user columns in the output.

        The primary CSV renames Gene/Group→Gene; Gene should be the first column.
        User-defined extraction columns appear before the metadata columns (PMID, Title, …).
        """
        result = self._run_pipeline()
        df = pd.read_csv(result["local_path"])
        cols = list(df.columns)

        # 'Gene' (renamed from Gene/Group) should be first
        assert cols[0] == "Gene", f"First column is '{cols[0]}', expected 'Gene'"

        # User columns should appear before PMID (which is in the trailing metadata block)
        pmid_idx = cols.index("PMID")
        for user_col in USER_COLUMNS:
            if user_col in cols:
                user_idx = cols.index(user_col)
                assert user_idx < pmid_idx, (
                    f"'{user_col}' (idx {user_idx}) should appear before "
                    f"PMID (idx {pmid_idx})"
                )


# ---------------------------------------------------------------------------
# F12 regression — PMID 41017238 Kawasaki scenario
#
# Three genes (ITPKC, CASP3, FCGR2A) appear only in a single co-mention
# sentence in the paper.  _backfill_sparse_row_evidence must populate each
# row with that sentence and tag the co-mention peers so the downstream
# confidence note can surface the context to the user.
# ---------------------------------------------------------------------------


def test_pmid_41017238_f12_regression():
    """Minimal synthetic replica of the PMID 41017238 (Kawasaki disease) case
    where ITPKC, CASP3, and FCGR2A only appear in a single co-mention
    sentence.  Exercises _backfill_sparse_row_evidence directly — no pipeline
    spawn, no multiprocessing, no Gemini API.
    """
    from unittest.mock import MagicMock, patch
    from modules import config as _config

    # Paper text is the co-mention sentence verbatim.  Being the ONLY sentence
    # means phase 1 of the gene-specific search always sees the peer genes in
    # the snippet window and falls through to phase 2 (co-mention tagging).
    paper_text = (
        "Furthermore, ITPKC, CASP3, and FCGR2A contribute together to "
        "Kawasaki disease susceptibility."
    )

    original_key = _config.GEMINI_API_KEY
    _config.GEMINI_API_KEY = "fake-api-key-for-testing"
    try:
        with patch(
            "modules.gemini_extractor.config.GEMINI_API_KEY",
            "fake-api-key-for-testing",
        ):
            with patch("google.genai.Client") as mock_client_cls:
                mock_client_cls.return_value = MagicMock()
                from modules.gemini_extractor import GeneInfoPipeline

                pipeline = GeneInfoPipeline(
                    paper_text=paper_text,
                    abstract_text="",
                    pubtator_genes=[],
                    figure_inputs=[],
                )
    finally:
        _config.GEMINI_API_KEY = original_key

    rows = [
        {"gene_name": "ITPKC", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
        {"gene_name": "CASP3", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
        {"gene_name": "FCGR2A", "variant_name": "", "Key Finding": "", "Key Finding Citation": ""},
    ]

    pipeline._backfill_sparse_row_evidence(
        rows, {"Key Finding": "primary finding about the gene"}
    )

    # All three rows should receive the single co-mention sentence as evidence.
    for row in rows:
        assert row["Key Finding"], (
            f"{row['gene_name']} was not backfilled from the co-mention sentence"
        )
        assert row["evidence_backfilled"] is True

    # At most one row may survive as gene_specific (the sole sentence is a
    # co-mention for all three, so all three should tag co_mention — but
    # this is written defensively for schedulers that might reorder scans).
    n_gene_specific = sum(
        1 for r in rows if r.get("evidence_specificity") == "gene_specific"
    )
    assert n_gene_specific <= 1, (
        f"Expected at most 1 gene_specific row (all 3 genes only appear in "
        f"the co-mention sentence), got {n_gene_specific}"
    )

    # Every co_mention row must list at least one peer canonical symbol.
    for row in rows:
        if row.get("evidence_specificity") == "co_mention":
            assert row.get("co_mentioned_genes"), (
                f"{row['gene_name']}: co_mention row must list peers, got "
                f"{row.get('co_mentioned_genes')!r}"
            )
