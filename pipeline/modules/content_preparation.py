"""Paper-level normalization artifacts shared by pipeline stages.

This module intentionally handles only paper text, citation text, abstracts,
and table indexes. Candidate-specific gene/variant normalization remains in
per-paper extraction, where provenance, HGNC aliases, and per-candidate caches are available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .gene_validator import (
    _extract_numbers,
    _normalize_citation_drift,
    _normalize_unicode_slashes,
)


@dataclass
class IndexedTableRow:
    label: str
    row_index: int
    row_text: str
    row_text_lower: str
    numbers: Tuple[str, ...]


@dataclass
class TableCitationIndex:
    """Precomputed table row text/numbers for citation validation."""

    tables: List[Dict[str, Any]] = field(default_factory=list)
    rows: List[IndexedTableRow] = field(default_factory=list)
    _gene_row_cache: Dict[Tuple[str, Tuple[str, ...]], List[IndexedTableRow]] = field(default_factory=dict)
    _citation_number_cache: Dict[str, Tuple[str, ...]] = field(default_factory=dict)

    @classmethod
    def from_tables(cls, tables: Optional[List[Dict[str, Any]]]) -> "TableCitationIndex":
        instance = cls(tables=list(tables or []))
        for table in instance.tables:
            label = str(table.get("label", table.get("table_id", "unknown")) or "unknown")
            for row_idx, row in enumerate(table.get("rows", []) or []):
                row_text = " ".join(str(cell) for cell in row)
                instance.rows.append(
                    IndexedTableRow(
                        label=label,
                        row_index=row_idx,
                        row_text=row_text,
                        row_text_lower=row_text.lower(),
                        numbers=tuple(_extract_numbers(row_text)),
                    )
                )
        return instance

    def numbers_for_citation(self, citation_text: str) -> Tuple[str, ...]:
        key = str(citation_text or "")
        if key not in self._citation_number_cache:
            self._citation_number_cache[key] = tuple(_extract_numbers(key))
        return self._citation_number_cache[key]

    def rows_for_gene(
        self,
        gene_symbol: str,
        gene_aliases: Optional[Iterable[str]] = None,
    ) -> List[IndexedTableRow]:
        symbols = [str(gene_symbol or "").strip().lower()]
        symbols.extend(str(alias or "").strip().lower() for alias in (gene_aliases or []))
        symbols = [symbol for symbol in symbols if symbol]
        cache_key = (
            str(gene_symbol or "").strip().lower(),
            tuple(sorted(set(symbols[1:]))),
        )
        if cache_key in self._gene_row_cache:
            return list(self._gene_row_cache[cache_key])

        patterns = [
            re.compile(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])")
            for symbol in symbols
        ]
        matches = [
            row
            for row in self.rows
            if any(pattern.search(row.row_text_lower) for pattern in patterns)
        ]
        self._gene_row_cache[cache_key] = list(matches)
        return matches


@dataclass(frozen=True)
class NormalizationRecord:
    """Deterministic paper-level evidence for normalized biomedical aliases."""

    original_mention: str
    normalized_gene: str
    normalized_variant: str
    evidence_sentence: str
    normalization_rule: str


GENE_ALIAS_RULES: Tuple[Tuple[str, str, re.Pattern[str]], ...] = (
    (
        "cytokine_alias_ifng",
        "IFNG",
        re.compile(
            r"(?<![A-Za-z0-9])(?:IFN[\s\-\u2010-\u2015]*(?:gamma|\u03b3)|interferon[\s\-\u2010-\u2015]+gamma)(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "cytokine_alias_tnf",
        "TNF",
        re.compile(
            r"(?<![A-Za-z0-9])TNF[\s\-\u2010-\u2015]*(?:alpha|\u03b1)(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
    (
        "protein_alias_mmp9",
        "MMP9",
        re.compile(
            r"(?<![A-Za-z0-9])MMP[\s\-\u2010-\u2015]*9(?![A-Za-z0-9])",
            re.IGNORECASE,
        ),
    ),
)

HLA_CLASS_I_CONTEXT_PATTERN = re.compile(
    r"\bHLA\b.{0,120}?\b(?:class\s*I\s*)?alleles?\b",
    re.IGNORECASE,
)
HLA_CLASS_I_ALLELE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([ABC])w?\*?(\d{2,4}(?::\d{2,4}){0,3})(?![A-Za-z0-9:])",
    re.IGNORECASE,
)
HLA_DIRECT_ALLELE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])HLA[\s\-]*([ABC])w?[\s\-]*\*?(\d{2,4}(?::\d{2,4}){0,3})(?![A-Za-z0-9:])",
    re.IGNORECASE,
)


def _iter_sentences(text: str) -> Iterable[str]:
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text or ""):
        sentence = " ".join(match.group(0).split())
        if sentence:
            yield sentence


def _canonical_hla_variant(locus: str, allele: str) -> Tuple[str, str]:
    """Return canonical HLA gene and gene-scoped allele variant."""
    locus_u = str(locus or "").strip().upper()
    allele_text = str(allele or "").strip()
    return f"HLA-{locus_u}", f"HLA-{locus_u}*{allele_text}"


def _is_part_of_direct_hla_allele(sentence: str, start: int) -> bool:
    """Avoid recording both `HLA-C*04` and nested shorthand `C*04`."""
    prefix = sentence[max(0, start - 8):start]
    return bool(re.search(r"HLA[\s\-]*$", prefix, re.IGNORECASE))


def _build_normalization_records(texts: Iterable[str]) -> List[NormalizationRecord]:
    records: List[NormalizationRecord] = []
    seen: set[Tuple[str, str, str, str, str]] = set()

    def add_record(record: NormalizationRecord) -> None:
        key = (
            record.original_mention,
            record.normalized_gene,
            record.normalized_variant,
            record.evidence_sentence,
            record.normalization_rule,
        )
        if key not in seen:
            seen.add(key)
            records.append(record)

    for text in texts:
        for sentence in _iter_sentences(text):
            for rule_name, normalized_gene, pattern in GENE_ALIAS_RULES:
                for match in pattern.finditer(sentence):
                    add_record(
                        NormalizationRecord(
                            original_mention=match.group(0),
                            normalized_gene=normalized_gene,
                            normalized_variant="",
                            evidence_sentence=sentence,
                            normalization_rule=rule_name,
                        )
                    )

            for match in HLA_DIRECT_ALLELE_PATTERN.finditer(sentence):
                gene, variant = _canonical_hla_variant(match.group(1), match.group(2))
                add_record(
                    NormalizationRecord(
                        original_mention=match.group(0),
                        normalized_gene=gene,
                        normalized_variant=variant,
                        evidence_sentence=sentence,
                        normalization_rule="hla_direct_allele",
                    )
                )

            if HLA_CLASS_I_CONTEXT_PATTERN.search(sentence):
                for match in HLA_CLASS_I_ALLELE_PATTERN.finditer(sentence):
                    if _is_part_of_direct_hla_allele(sentence, match.start()):
                        continue
                    gene, variant = _canonical_hla_variant(match.group(1), match.group(2))
                    add_record(
                        NormalizationRecord(
                            original_mention=match.group(0),
                            normalized_gene=gene,
                            normalized_variant=variant,
                            evidence_sentence=sentence,
                            normalization_rule="hla_class_i_allele_shorthand",
                        )
                    )

    return records


@dataclass
class PreparedPaperContent:
    """Paper-level normalized artifacts handed from preparation into per-paper extraction."""

    raw_text: str
    citation_text_normalized: str
    abstract_text_normalized: str
    table_inputs: List[Dict[str, Any]]
    table_citation_index: TableCitationIndex
    normalization_notes: Dict[str, Any] = field(default_factory=dict)
    normalization_records: List[NormalizationRecord] = field(default_factory=list)

    def records_for_gene(self, gene_symbol: str) -> List[NormalizationRecord]:
        target = str(gene_symbol or "").strip().upper()
        return [
            record
            for record in self.normalization_records
            if record.normalized_gene.upper() == target
        ]

    def records_for_variant(self, variant: str) -> List[NormalizationRecord]:
        target = str(variant or "").strip().upper()
        return [
            record
            for record in self.normalization_records
            if record.normalized_variant.upper() == target
        ]

    @classmethod
    def from_raw(
        cls,
        paper_text: str,
        abstract_text: str = "",
        table_inputs: Optional[List[Dict[str, Any]]] = None,
    ) -> "PreparedPaperContent":
        raw_text = paper_text or ""
        abstract = abstract_text or ""
        tables = list(table_inputs or [])
        citation_text_normalized = _normalize_citation_drift(
            _normalize_unicode_slashes(raw_text)
        )
        abstract_text_normalized = _normalize_citation_drift(
            _normalize_unicode_slashes(abstract)
        )
        table_index = TableCitationIndex.from_tables(tables)
        normalization_records = _build_normalization_records((raw_text, abstract))
        return cls(
            raw_text=raw_text,
            citation_text_normalized=citation_text_normalized,
            abstract_text_normalized=abstract_text_normalized,
            table_inputs=tables,
            table_citation_index=table_index,
            normalization_records=normalization_records,
            normalization_notes={
                "citation_text_normalized": True,
                "abstract_text_normalized": bool(abstract),
                "table_rows_indexed": len(table_index.rows),
                "normalization_records": len(normalization_records),
            },
        )
