"""
Shared pytest fixtures for the ResearchShop pipeline test suite.

All fixtures are offline — no Gemini API, NCBI, or network access required.
The HGNC JSON is loaded from the bundled local database file.
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure `local_pivot/python/` is on sys.path so `import modules.*` works
# regardless of which directory pytest is invoked from.
_PYTHON_ROOT = Path(__file__).parent.parent
if str(_PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(_PYTHON_ROOT))

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Text fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def molecular_genetics_abstract() -> str:
    """Molecular genetics abstract that should pass abstract screening (score ≥ 5)."""
    return (
        "Somatic mutations in BRCA1 and TP53 genes were identified in patients with "
        "triple-negative breast cancer. Whole-exome sequencing revealed 45 coding variants "
        "including frameshift deletions in BRCA2 and missense mutations such as p.Val600Glu "
        "in BRAF. SNP genotyping of rs1799943 was performed on 500 samples. Gene expression "
        "analysis showed overexpression of ERBB2 and downregulation of PTEN by RNA-seq. "
        "CRISPR knockout of CDH1 confirmed its causal role in metastasis. GWAS identified "
        "12 new susceptibility loci associated with breast cancer risk."
    )


@pytest.fixture
def molecular_genetics_title() -> str:
    return "Whole-exome sequencing reveals BRCA1 and TP53 mutations in triple-negative breast cancer"


@pytest.fixture
def clinical_epidemiology_abstract() -> str:
    """Clinical epidemiology abstract that should fail abstract screening."""
    return (
        "A systematic review and meta-analysis of randomized controlled trials evaluating "
        "rehabilitation outcomes in elderly patients with hip fractures. Quality of life "
        "scores were assessed using the SF-36 instrument. Patient education and nursing care "
        "protocols were compared across health care settings. Cost-effectiveness analysis "
        "showed an economic burden of $12,500 per patient. Access to care disparities were "
        "noted in rural versus urban populations. Policy implications are discussed."
    )


@pytest.fixture
def clinical_epidemiology_title() -> str:
    return "Rehabilitation outcomes in elderly hip fracture patients: a systematic review"


@pytest.fixture
def sample_paper_text() -> str:
    """Realistic prose-rich paper text for citation grounding tests."""
    return (
        "Introduction\n"
        "BRCA1 mutations are associated with increased risk of breast and ovarian cancer. "
        "Several studies have shown that patients carrying the BRCA1 c.5266dupC (5382insC) "
        "mutation have a 70% lifetime risk of developing breast cancer.\n\n"
        "Results\n"
        "We identified 127 patients with pathogenic BRCA1 variants. "
        "The most common variant was p.Glu1915Ter (E1915X), found in 45 patients (35%). "
        "TP53 mutations were detected in 23% of triple-negative breast cancer cases. "
        "The 5-year overall survival rate was 78.3% (95% CI: 72.1-84.5%).\n\n"
        "Conclusion\n"
        "BRCA1 and TP53 mutations are the most frequent alterations in this cohort. "
        "BRCA2 variants were found in 12% of BRCA1-negative cases. "
        "These findings confirm the role of homologous recombination deficiency in "
        "triple-negative breast cancer."
    )


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pmc_xml_bytes() -> bytes:
    """Raw bytes of the minimal PMC JATS XML fixture."""
    xml_path = FIXTURES_DIR / "pmc_minimal.xml"
    return xml_path.read_bytes()


@pytest.fixture
def pubtator_bioc_doc() -> dict:
    """Single BioC JSON document (first entry from the fixture array)."""
    json_path = FIXTURES_DIR / "pubtator_brca1.json"
    docs = json.loads(json_path.read_text())
    return docs[0]
