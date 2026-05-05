"""DataFrame metadata annotation for per-paper extraction output rows."""

import logging
import re
from typing import Any, Dict, List

import pandas as pd

from .. import config
from ..association_policy import association_group_for_type


class MetadataMixin:
    def _collect_debug_artifact(self) -> Dict[str, Any]:
        """
        Build a serializable debug artifact describing candidate lifecycle and drops.
        """
        candidates: List[Dict[str, Any]] = []
        for meta in self.candidate_meta.values():
            candidates.append(
                {
                    "gene": str(meta.get("gene") or ""),
                    "variant": self._normalize_variant_value(meta.get("variant", "")),
                    "sources": self._as_sorted_strings(meta.get("sources")),
                    "raw_gene_labels": self._as_sorted_strings(meta.get("raw_gene_labels")),
                    "candidate_terms": list(meta.get("candidate_terms") or []),
                    "association_type": str(meta.get("association_type") or ""),
                    "association_group": association_group_for_type(
                        str(meta.get("association_type") or "")
                    ),
                    "normalization_applied": str(meta.get("normalization_applied") or ""),
                    "validation_confidence": meta.get("validation_confidence"),
                    "validation_source": str(meta.get("validation_source") or ""),
                    "validation_outcome": str(meta.get("validation_outcome") or ""),
                    "deterministic_context_reason": str(
                        meta.get("deterministic_context_reason") or ""
                    ),
                    "deterministic_context_snippet": str(
                        meta.get("deterministic_context_snippet") or ""
                    ),
                }
            )

        return {
            "candidate_count": len(candidates),
            "candidates": candidates,
            "detail_extraction_status": self.detail_extraction_status,
            "detail_extraction_error": self.detail_extraction_error,
            "quota_limited": self._quota_limited,
            "detail_extraction_rows": self.detail_extraction_rows,
            "validation_drops": list(self.dropped_candidates),
            "strict_gate_drops": list(self.strict_gate_drops),
            "evidence_gate_drops": list(self.evidence_gate_drops),
            "table_inputs_count": len(self.table_inputs),
            "figure_inputs_count": len(self.figure_inputs),
            "pubtator_genes_count": len(self.pubtator_genes),
            "paper_text_length": len(self.paper_text or ""),
            "api_calls_this_paper": self._paper_api_calls,
            "context_warning": self._context_warning,
            "truncation_rescue_count": self._truncation_rescue_count,
            "final_associations": [
                {
                    "gene": str((assoc.get("gene") if isinstance(assoc, dict) else assoc[0]) or ""),
                    "variant": self._normalize_variant_value(
                        assoc.get("variant", "")
                        if isinstance(assoc, dict)
                        else (assoc[1] if len(assoc) > 1 else "")
                    ),
                    "association_type": str(assoc.get("association_type", ""))
                    if isinstance(assoc, dict)
                    else "",
                    "association_group": association_group_for_type(
                        str(assoc.get("association_type", ""))
                        if isinstance(assoc, dict)
                        else ""
                    ),
                }
                for assoc in (self.associations or [])
            ],
        }

    def _add_candidate_provenance_metadata(self, df: pd.DataFrame):
        """
        Add candidate lifecycle provenance columns to aid trust/debugging.
        """
        if df.empty:
            return

        df["Candidate Source"] = ""
        df["Normalization Applied"] = ""
        df["Validation Outcome"] = ""
        df["Association Type"] = ""
        df["Association Group"] = ""
        df["Dropped By Gate"] = False
        df["Deterministic Context Reason"] = ""
        df["Deterministic Context Evidence"] = ""

        for i, row in df.iterrows():
            gene = (row.get("gene_name") or "").strip()
            variant = self._normalize_variant_value(row.get("variant_name", ""))
            key = self._assoc_key(gene, variant)
            meta = self.candidate_meta.get(key)
            if not meta:
                continue

            df.at[i, "Candidate Source"] = ",".join(
                self._as_sorted_strings(meta.get("sources"))
            )

            df.at[i, "Normalization Applied"] = meta.get("normalization_applied", "") or ""
            df.at[i, "Validation Outcome"] = meta.get("validation_outcome", "") or ""
            association_type = self._infer_row_association_type(row, meta)
            df.at[i, "Association Type"] = association_type
            df.at[i, "Association Group"] = association_group_for_type(association_type)
            df.at[i, "Deterministic Context Reason"] = (
                meta.get("deterministic_context_reason", "") or ""
            )
            df.at[i, "Deterministic Context Evidence"] = (
                meta.get("deterministic_context_snippet", "") or ""
            )

    def _add_validation_metadata(self, df: pd.DataFrame):
        """
        Add validation metadata to the results DataFrame.

        Args:
            df: DataFrame with extracted gene information
        """
        if not self.validation_results:
            return

        # Create validation metadata columns
        df["validation_confidence"] = 0.0
        df["validation_source"] = "unknown"
        df["validation_suggestions"] = ""
        df["Gene Biotype"] = "unknown"

        validation_by_key = {
            self._assoc_key(result.gene, self._normalize_variant_value(result.variant)): result
            for result in self.validation_results
        }

        for i, row in df.iterrows():
            gene_name = str(row.get("gene_name", "") or "").strip().upper()
            variant_name = self._normalize_variant_value(row.get("variant_name", ""))
            key = self._assoc_key(gene_name, variant_name)

            # Look up gene biotype from local HGNC database
            if gene_name:
                df.at[i, "Gene Biotype"] = self.gene_validator.get_gene_biotype(gene_name)

            result = validation_by_key.get(key)
            if result:
                df.at[i, "validation_confidence"] = result.confidence_score
                df.at[i, "validation_source"] = result.validation_source
                df.at[i, "validation_suggestions"] = (
                    "; ".join(result.suggestions) if result.suggestions else ""
                )

        logging.info(f"Added validation metadata to {len(df)} result rows")

    def _add_citation_validation_metadata(self, df: pd.DataFrame):
        """
        Add citation validation metadata to the results DataFrame.

        For each user-defined column pair (e.g. "Key Finding" / "Key Finding Citation"),
        validates that the citation text actually appears in the paper and records
        the result in three columns:
          {field}_citation_valid       — bool: citation grounded in paper
          {field}_citation_confidence  — float 0–1: match confidence
          {field}_citation_details     — str: human-readable reason

        Root cause of previous broken implementation: the old code called
        validate_citations(row.to_dict(), ...) which iterated ALL row fields
        including floats and Nones, causing re.search() to raise TypeError.
        The inner except silently swallowed it, leaving every row at the
        'No validation performed' default. Fixed by pairing content columns
        with their Citation siblings directly and validating the citation text.
        """
        if not config.ENABLE_CITATION_VALIDATION:
            return
        if not getattr(self, "paper_text", None):
            return

        from ..gene_validator import (
            _calculate_citation_confidence,
            _citation_exists_in_paper,
            _normalize_citation_drift,
            _normalize_unicode_slashes,
        )

        excluded_cols = {
            "gene_name",
            "variant_name",
            "Gene/Group",
            "Variant Name",
            "validation_confidence",
            "validation_source",
            "validation_suggestions",
            "context_flash_fits",
            "context_pro_fits",
            "context_original_tokens",
            "context_modifications",
            "context_truncation_applied",
            "PMID",
            "DOI",
            "Study Title",
            "Authors",
            "Publication Year",
            "Journal Name",
            "Author Affiliations",
            "Citations",
            "Citation Source",
            "Citation Retrieved At",
            "iCite Citations",
            "Semantic Scholar Citations",
            "Abstract",
            "Figure Count",
            "Figure Analysis Enabled",
            "Metadata Completeness",
            "Metadata Warnings",
            "Gene Source",
            "NCBI Gene ID",
            "Gene Full Name",
            "Gene Aliases",
            "Gene Biotype",
            "Chromosome",
            "Candidate Source",
            "Normalization Applied",
            "Validation Outcome",
            "Association Type",
            "Association Group",
            "Dropped By Gate",
        }

        # Find (content_col, citation_col) pairs: columns where {col} Citation also exists.
        # These are the LLM-extracted evidence fields we want to validate.
        pairs = []
        for col in df.columns:
            if (
                col in excluded_cols
                or col.endswith(" Citation")
                or col.endswith("_citation_valid")
                or col.endswith("_citation_confidence")
                or col.endswith("_citation_details")
            ):
                continue
            citation_col = f"{col} Citation"
            if citation_col in df.columns:
                pairs.append((col, citation_col))

        if not pairs:
            return

        # Initialise all validation meta-columns with 'No citation provided' defaults
        for content_col, citation_col in pairs:
            for col in (content_col, citation_col):
                df[f"{col}_citation_valid"] = False
                df[f"{col}_citation_confidence"] = 0.0
                df[f"{col}_citation_details"] = "No citation provided"

        total_validated = 0
        total_found = 0
        if not getattr(self, "_citation_paper_text_cache", None):
            self._citation_paper_text_cache = _normalize_citation_drift(
                _normalize_unicode_slashes(self.paper_text)
            )
        normalized_paper_text = self._citation_paper_text_cache
        citation_cache: Dict[tuple, tuple] = {}

        for i, row in df.iterrows():
            gene_symbol = str(row.get("gene_name", row.get("Gene/Group", "")))

            # Collect raw pre-normalization labels for this gene (e.g. "BNP" for NPPB).
            # Papers use aliases, not HGNC canonical symbols, so the gene context check
            # must accept any of: canonical symbol OR any raw label.
            variant_symbol = str(row.get("variant_name", "")).strip()
            meta_key = (gene_symbol.upper(), variant_symbol.upper())
            meta = self.candidate_meta.get(meta_key) or {}
            raw_labels = self._as_sorted_strings(meta.get("raw_gene_labels"))

            for content_col, citation_col in pairs:
                raw = row.get(citation_col, "")
                citation_text = str(raw).strip() if raw is not None and str(raw) != "nan" else ""

                # Skip empty fields and backfill placeholder — not real LLM citations
                if not citation_text or citation_text == "Auto snippet from paper text":
                    continue

                try:
                    cache_key = (
                        citation_text,
                        gene_symbol.upper(),
                        tuple(raw_labels),
                    )
                    if cache_key in citation_cache:
                        exists, ratio, reason, confidence = citation_cache[cache_key]
                    else:
                        exists, ratio, reason = _citation_exists_in_paper(
                            citation_text,
                            normalized_paper_text,
                            gene_symbol,
                            gene_aliases=raw_labels,
                            tables=self.table_inputs,
                            paper_text_pre_normalized=True,
                            table_index=getattr(self, "table_citation_index", None),
                        )
                        confidence = _calculate_citation_confidence(
                            citation_text, normalized_paper_text, exists, ratio
                        )
                        citation_cache[cache_key] = (exists, ratio, reason, confidence)
                    is_valid = exists and confidence >= config.CITATION_MIN_CONFIDENCE

                    # Write results to both the content column and its Citation sibling
                    for col in (content_col, citation_col):
                        df.at[i, f"{col}_citation_valid"] = is_valid
                        df.at[i, f"{col}_citation_confidence"] = round(confidence, 3)
                        df.at[i, f"{col}_citation_details"] = reason

                    total_validated += 1
                    if is_valid:
                        total_found += 1

                except Exception as e:
                    logging.warning(f"Citation validation error [{content_col}] row {i}: {e}")

        if total_validated:
            pct = total_found / total_validated * 100
            logging.info(
                f"Citation validation: {total_found}/{total_validated} grounded ({pct:.1f}%)"
            )
        logging.info(
            f"Citation validation metadata added to {len(df)} rows ({len(pairs)} field pairs)"
        )

    def _infer_row_association_type(self, row: pd.Series, meta: Dict[str, Any]) -> str:
        """Classify row intent for reviewer-friendly output filtering."""
        base_type = str(meta.get("association_type") or "")
        if base_type in {"variant_association", "susceptibility_gene", "figure_derived_gene"}:
            return base_type

        excluded_columns = {
            "Gene/Group",
            "Variant Name",
            "PMID",
            "DOI",
            "Study Title",
            "Authors",
            "Publication Year",
            "Journal Name",
            "Author Affiliations",
            "Citations",
            "Abstract",
            "Candidate Source",
            "Normalization Applied",
            "Validation Outcome",
            "Association Type",
            "Association Group",
        }
        text = " ".join(
            str(row.get(col, "") or "")
            for col in row.index
            if not str(col).endswith("_citation_valid")
            and col not in excluded_columns
            and not str(col).startswith(("validation_", "context_"))
        ).lower()

        if "genome wide association" in text or "susceptibility" in text or "polymorphism" in text:
            return "susceptibility_gene"
        if "knockout" in text or " ko " in f" {text} " or "murine model" in text or "mouse model" in text:
            return "animal_model_gene"
        if "biomarker" in text or "serum level" in text or "diagnos" in text:
            return "biomarker_response_gene"
        if (
            "pathway" in text
            or "signaling" in text
            or "nf kappab" in text
            or re.search(r"\bmapk\b", text)
        ):
            return "mechanistic_pathway_gene"
        return base_type or self._infer_candidate_association_type(meta)

    def _add_context_metadata(self, df: pd.DataFrame, context_validation: Dict[str, Any]):
        """
        Add context window validation metadata to the results DataFrame.

        Args:
            df: DataFrame with extracted gene information
            context_validation: Results from context validation
        """
        # Add context validation columns
        df["context_flash_fits"] = context_validation["flash_fits"]
        df["context_pro_fits"] = context_validation["pro_fits"]
        df["context_original_tokens"] = context_validation["original_tokens"]
        df["context_modifications"] = context_validation["modifications"]
        df["context_truncation_applied"] = context_validation["truncation_applied"]
        df["context_truncated"] = context_validation.get("context_truncated", False)

        # Log context validation summary
        if context_validation.get("context_truncated"):
            logging.warning(f"Context truncation warning: {context_validation['modifications']}")
        elif context_validation["truncation_applied"]:
            logging.warning(f"Context truncation applied: {context_validation['modifications']}")
        else:
            logging.info("No context truncation needed")
