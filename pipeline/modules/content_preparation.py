"""Paper-level normalization artifacts shared by pipeline stages.

This module intentionally handles only paper text, citation text, abstracts,
and table indexes. Candidate-specific gene/variant normalization remains in
Stage 5, where provenance, HGNC aliases, and per-candidate caches are available.
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


@dataclass
class PreparedPaperContent:
    """Paper-level normalized artifacts handed from preparation into Stage 5."""

    raw_text: str
    citation_text_normalized: str
    abstract_text_normalized: str
    table_inputs: List[Dict[str, Any]]
    table_citation_index: TableCitationIndex
    normalization_notes: Dict[str, Any] = field(default_factory=dict)

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
        return cls(
            raw_text=raw_text,
            citation_text_normalized=citation_text_normalized,
            abstract_text_normalized=abstract_text_normalized,
            table_inputs=tables,
            table_citation_index=table_index,
            normalization_notes={
                "citation_text_normalized": True,
                "abstract_text_normalized": bool(abstract),
                "table_rows_indexed": len(table_index.rows),
            },
        )
