"""Focused tests for paper-level content preparation artifacts."""

from modules.content_preparation import PreparedPaperContent


def test_prepared_content_indexes_cytokine_alias_without_changing_raw_text():
    raw_text = (
        "The cytokine response included IFN-gamma, IFN-\u03b3, and interferon gamma induction in stimulated cells. "
        "TNF-alpha was also elevated."
    )

    prepared = PreparedPaperContent.from_raw(raw_text)

    assert prepared.raw_text == raw_text

    ifng_records = prepared.records_for_gene("IFNG")
    assert [record.original_mention for record in ifng_records] == [
        "IFN-gamma",
        "IFN-\u03b3",
        "interferon gamma",
    ]
    assert {record.normalized_gene for record in ifng_records} == {"IFNG"}
    assert {record.normalized_variant for record in ifng_records} == {""}
    assert ifng_records[0].evidence_sentence == (
        "The cytokine response included IFN-gamma, IFN-\u03b3, and interferon gamma induction in stimulated cells."
    )
    assert ifng_records[0].normalization_rule == "cytokine_alias_ifng"

    tnf_records = prepared.records_for_gene("TNF")
    assert len(tnf_records) == 1
    assert tnf_records[0].original_mention == "TNF-alpha"
    assert tnf_records[0].normalized_gene == "TNF"
    assert tnf_records[0].normalization_rule == "cytokine_alias_tnf"


def test_prepared_content_indexes_hla_class_i_allele_shorthand():
    raw_text = (
        "We typed HLA class I alleles A*02, B*35 and C*04 in the cohort. "
        "The genotype frequencies were compared by outcome."
    )

    prepared = PreparedPaperContent.from_raw(raw_text)

    assert prepared.raw_text == raw_text

    hla_c_records = prepared.records_for_gene("HLA-C")
    assert len(hla_c_records) == 1
    assert hla_c_records[0].original_mention == "C*04"
    assert hla_c_records[0].normalized_gene == "HLA-C"
    assert hla_c_records[0].normalized_variant == "HLA-C*04"
    assert hla_c_records[0].evidence_sentence == (
        "We typed HLA class I alleles A*02, B*35 and C*04 in the cohort."
    )
    assert hla_c_records[0].normalization_rule == "hla_class_i_allele_shorthand"
    assert prepared.records_for_variant("HLA-C*04") == hla_c_records


def test_prepared_content_indexes_direct_and_compact_hla_alleles():
    raw_text = (
        "HLA-C*04:01 was enriched in cases. "
        "A replication cohort reported HLA-C04 and Cw*06 in HLA class I alleles."
    )

    prepared = PreparedPaperContent.from_raw(raw_text)

    hla_c_records = prepared.records_for_gene("HLA-C")
    payloads = {
        (record.original_mention, record.normalized_variant, record.normalization_rule)
        for record in hla_c_records
    }

    assert ("HLA-C*04:01", "HLA-C*04:01", "hla_direct_allele") in payloads
    assert ("HLA-C04", "HLA-C*04", "hla_direct_allele") in payloads
    assert ("Cw*06", "HLA-C*06", "hla_class_i_allele_shorthand") in payloads


def test_prepared_content_indexes_mmp9_hyphenated_alias():
    raw_text = "MMP-9 was elevated as a matrisome-related inflammatory marker in MIS-C."

    prepared = PreparedPaperContent.from_raw(raw_text)

    records = prepared.records_for_gene("MMP9")
    assert len(records) == 1
    assert records[0].original_mention == "MMP-9"
    assert records[0].normalized_gene == "MMP9"
    assert records[0].normalization_rule == "protein_alias_mmp9"


def test_prepared_content_does_not_perform_broad_clinical_alias_resolution():
    raw_text = (
        "BNP and NT-proBNP were measured as cardiac biomarkers in the cohort. "
        "These clinical markers were not used as gene-expression evidence."
    )

    prepared = PreparedPaperContent.from_raw(raw_text)

    assert prepared.raw_text == raw_text
    assert prepared.records_for_gene("NPPB") == []
