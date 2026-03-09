"""
Tests for abstract_screener.has_genetic_content()

No network calls — pure keyword/regex scoring.
"""

from modules.abstract_screener import has_genetic_content


def test_molecular_genetics_abstract_passes(molecular_genetics_abstract, molecular_genetics_title):
    """Molecular genetics paper with GWAS, mutations, gene symbols should pass (score ≥ 5)."""
    should_process, confidence, details = has_genetic_content(
        molecular_genetics_abstract,
        molecular_genetics_title,
    )
    assert should_process is True, (
        f"Expected molecular genetics abstract to pass screening. "
        f"Raw score={details['raw_score']}, threshold={details['threshold']}"
    )
    assert confidence > 0.0


def test_clinical_epidemiology_abstract_rejected(
    clinical_epidemiology_abstract, clinical_epidemiology_title
):
    """Pure epidemiology/rehabilitation paper with negative keywords should be rejected."""
    should_process, confidence, details = has_genetic_content(
        clinical_epidemiology_abstract,
        clinical_epidemiology_title,
    )
    assert should_process is False, (
        f"Expected clinical epidemiology abstract to be rejected. "
        f"Raw score={details['raw_score']}, threshold={details['threshold']}"
    )


def test_gene_symbol_pattern_boosts_score():
    """Gene symbol patterns (e.g. BRCA1, TP53) should increase the raw score."""
    abstract_with_genes = (
        "We studied BRCA1 and TP53 expression in tumor samples. "
        "Gene knockout experiments confirmed the role of PTEN in cell proliferation. "
        "Protein levels of EGFR were measured by Western blot in 50 patient samples."
    )
    _, _, details_with = has_genetic_content(abstract_with_genes, "Gene study")

    abstract_no_genes = (
        "We studied protein levels and enzyme activity in tumor samples. "
        "Knockout experiments confirmed the role of signaling in cell proliferation. "
        "Protein levels were measured by Western blot in 50 patient samples."
    )
    _, _, details_without = has_genetic_content(abstract_no_genes, "Protein study")

    assert details_with["raw_score"] > details_without["raw_score"], (
        "Gene symbol patterns should increase raw score"
    )


def test_short_abstract_rejected():
    """Abstracts shorter than 100 chars should be rejected immediately."""
    should_process, confidence, details = has_genetic_content("Too short.", "Title")
    assert should_process is False
    assert confidence == 0.0
    assert details.get("reason") == "abstract_too_short"


def test_variant_nomenclature_boosts_score():
    """HGVS variant patterns (p.Val600Glu, rs123456) should increase the score."""
    abstract = (
        "Patients carried the BRAF p.Val600Glu mutation (rs113488022). "
        "Additional variants c.1799T>A were found in 30% of melanoma samples. "
        "SNP rs28897672 was associated with BRCA1-related cancer risk in the cohort."
    )
    _, _, details = has_genetic_content(abstract, "BRAF mutation study")
    assert details["variant_count"] >= 1, "Expected at least one variant pattern match"
    assert details["raw_score"] >= 5, "Variant-rich abstract should pass screening"


def test_clinical_biomarker_paper_rejected():
    """Clinical outcome paper mentioning gene-like biomarkers (IL6, CRP) without
    molecular context should be rejected by the molecular-context precision gate."""
    abstract = (
        "We measured serum levels of CRP, IL6, and BNP in 200 children with "
        "multisystem inflammatory syndrome. Cytokine levels were significantly "
        "elevated compared to healthy controls. Biomarker concentrations were "
        "correlated with disease severity. Interleukin levels decreased after "
        "treatment with intravenous immunoglobulin. Ferritin and D-dimer were "
        "also elevated. No significant differences in clinical outcomes were "
        "observed between treatment groups at 30-day follow-up."
    )
    should_process, _, details = has_genetic_content(
        abstract,
        "Biomarker levels in multisystem inflammatory syndrome in children",
    )
    assert details["has_molecular_context"] is False, (
        "Clinical biomarker paper should lack molecular context"
    )
    assert details["molecular_context_penalty"] > 0, (
        "Molecular context penalty should be applied"
    )
    assert should_process is False, (
        f"Clinical biomarker paper should be rejected. "
        f"Raw score={details['raw_score']}, threshold={details['threshold']}"
    )


def test_molecular_context_not_penalized():
    """Papers with molecular context terms should not receive a penalty."""
    abstract = (
        "We performed whole-exome sequencing on 50 patients and identified "
        "somatic mutations in IL6 and STAT3. Gene expression analysis revealed "
        "significant overexpression of JAK2 in treatment-resistant samples. "
        "Knockdown of STAT3 reduced cell proliferation by 60 percent."
    )
    should_process, _, details = has_genetic_content(
        abstract,
        "Somatic mutations in the JAK-STAT pathway",
    )
    assert details["has_molecular_context"] is True
    assert details["molecular_context_penalty"] == 0
    assert should_process is True
