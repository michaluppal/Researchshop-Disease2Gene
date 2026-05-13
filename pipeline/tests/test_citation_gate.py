import pandas as pd

from modules.paper_analysis.evidence import EvidenceMixin


class DummyEvidenceGate(EvidenceMixin):
    def __init__(self):
        self.evidence_gate_drops = []

    def _normalize_variant_for_gene(self, gene, variant):
        return str(variant or "").strip().upper()


def test_citation_gate_drops_row_when_all_provided_citations_are_invalid(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "ENABLE_STRICT_CITATION_GATE", True)
    gate = DummyEvidenceGate()
    df = pd.DataFrame(
        [
            {
                "gene_name": "BRCA1",
                "variant_name": "p.Glu1915Ter",
                "Key Finding Citation": "fabricated sentence",
                "Key Finding_citation_valid": False,
                "Key Finding Citation_citation_valid": False,
                "Key Finding_citation_details": "Citation text not found in paper",
            }
        ]
    )

    filtered = gate._apply_citation_gate(df, {"Key Finding": "finding"})

    assert filtered.empty
    assert gate.evidence_gate_drops[0]["reason"] == "ungrounded_citation"
    assert gate.evidence_gate_drops[0]["gene"] == "BRCA1"


def test_citation_gate_keeps_row_with_at_least_one_grounded_citation(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "ENABLE_STRICT_CITATION_GATE", True)
    gate = DummyEvidenceGate()
    df = pd.DataFrame(
        [
            {
                "gene_name": "BRCA1",
                "variant_name": "",
                "Key Finding Citation": "BRCA1 appeared in the source text.",
                "Key Finding_citation_valid": True,
                "Statistical Evidence Citation": "fabricated p-value",
                "Statistical Evidence_citation_valid": False,
            }
        ]
    )

    filtered = gate._apply_citation_gate(
        df,
        {
            "Key Finding": "finding",
            "Statistical Evidence": "statistics",
        },
    )

    assert len(filtered) == 1
    assert gate.evidence_gate_drops == []


def test_citation_gate_leaves_empty_citation_rows_to_evidence_gate(monkeypatch):
    from modules import config

    monkeypatch.setattr(config, "ENABLE_STRICT_CITATION_GATE", True)
    gate = DummyEvidenceGate()
    df = pd.DataFrame(
        [
            {
                "gene_name": "BRCA1",
                "variant_name": "",
                "Key Finding": "BRCA1 appeared in the source text.",
                "Key Finding Citation": "",
            }
        ]
    )

    filtered = gate._apply_citation_gate(df, {"Key Finding": "finding"})

    assert len(filtered) == 1
    assert gate.evidence_gate_drops == []
