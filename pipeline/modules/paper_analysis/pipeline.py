"""Per-paper extraction coordinator."""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from .. import config, pipeline_tracer
from ..content_preparation import PreparedPaperContent
from ..gene_validator import ContextWindowValidator, GeneValidator
from .candidates import CandidateMixin
from .context import ContextMixin
from .evidence import EvidenceMixin
from .figures import FigureMixin
from .gemini_client import GeminiClientMixin
from .metadata import MetadataMixin


class PaperAnalysisPipeline(
    GeminiClientMixin,
    CandidateMixin,
    EvidenceMixin,
    FigureMixin,
    MetadataMixin,
    ContextMixin,
):
    def __init__(
        self,
        paper_text: str,
        abstract_text: str = "",
        pubtator_genes: List[str] = None,
        figure_inputs: List[Dict[str, Any]] = None,
        table_inputs: List[Dict[str, Any]] = None,
        pmid: Optional[str] = None,
        prepared_content: Optional[PreparedPaperContent] = None,
        client: Optional[Any] = None,
    ):
        if client is None and not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in the configuration.")
        self.pmid = pmid  # used only for the pipeline tracer
        self.prepared_content = prepared_content or PreparedPaperContent.from_raw(
            paper_text=paper_text,
            abstract_text=abstract_text,
            table_inputs=table_inputs or [],
        )
        self.paper_text = self.prepared_content.raw_text
        self.abstract_text = abstract_text  # Store abstract separately
        self.original_paper_text = self.prepared_content.raw_text  # Keep original for reference
        self.associations = []
        self.validated_associations = []
        self.validation_results = []
        self.context_validation_results = {}
        self.dropped_candidates: List[Dict[str, Any]] = []
        self.strict_gate_drops: List[Dict[str, Any]] = []
        self.evidence_gate_drops: List[Dict[str, Any]] = []
        self.detail_extraction_status: str = "not_started"
        self.detail_extraction_error: str = ""
        self.detail_extraction_rows: int = 0
        self.candidate_meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._hgnc_alias_cache: Dict[str, List[str]] = {}
        self._candidate_terms_cache: Dict[Tuple[str, str], List[str]] = {}
        self._citation_paper_text_cache: Optional[str] = (
            self.prepared_content.citation_text_normalized
        )

        # Hybrid pipeline: PubTator genes passed in from orchestrator
        self.pubtator_genes = pubtator_genes or []
        self.figure_inputs = figure_inputs or []
        self.table_inputs = self.prepared_content.table_inputs
        self.table_citation_index = self.prepared_content.table_citation_index
        self._paper_api_calls: int = 0
        self._last_gemini_call_at: Optional[float] = None
        self._quota_limited: bool = False
        self._context_warning: Optional[str] = None
        self._truncation_rescue_count: int = 0

        if client is None:
            # Lazy import to avoid top-level import failures
            from google import genai  # type: ignore

            self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        else:
            self.client = client
        self.gene_validator = GeneValidator()
        self.context_validator = ContextWindowValidator()

    def run_pipeline(self, column_descriptions):
        """
        Run extraction end-to-end and return a DataFrame with gene and citation validation heuristics.

        Stages:
          0   — Context window validation and truncation
          0.5–1.5 — Candidate discovery (abstract, full-text ×2, deterministic, figures, PubTator)
          1.6 — Grounding check (drop hallucinated candidates)
          2   — Gene validation heuristics + normalization
          3   — Detail extraction (Stage 3 LLM call)
          4   — Post-validation (strict gate, citation validation, evidence gate)
        """
        # Step 0: Validate and prepare paper text for context windows
        logging.info("Step 0: Validating paper text against model context limits")
        with pipeline_tracer.stage("context_validation"):
            context_validation = self._validate_and_prepare_paper_text()

        if context_validation["failed"]:
            logging.error("Context validation failed - cannot proceed with pipeline")
            return pd.DataFrame()

        # Steps 0.5–1.5: Candidate discovery
        self._run_candidate_discovery()

        # Step 1.6: Grounding check
        with pipeline_tracer.stage("grounding_check"):
            self._run_grounding_check()

        # Step 2: Gene validation + normalization
        with pipeline_tracer.stage("hgnc_validation"):
            self._run_validation_and_normalize()

        # Step 3: Detail extraction
        with pipeline_tracer.stage("detail_extraction"):
            extracted_info = self._run_detail_extraction(column_descriptions)
        if not extracted_info:
            return pd.DataFrame()

        # Step 4: Post-validation (metadata, strict gate, citation, evidence gate)
        df = pd.DataFrame(extracted_info)
        if "variant_name" in df.columns:
            df["variant_name"] = df["variant_name"].apply(self._normalize_variant_value)
        return self._run_post_validation(df, column_descriptions, context_validation)

    def _summarise_sources(self) -> Dict[str, int]:
        """Tracer helper: how many candidates carry each source tag."""
        counts: Dict[str, int] = {}
        for meta in self.candidate_meta.values():
            for src in self._as_string_set(meta.get("sources")):
                counts[src] = counts.get(src, 0) + 1
        return counts

    def _run_candidate_discovery(self) -> None:
        """Steps 0.5–1.5: Discover gene candidates from all sources."""
        # Reset candidate tracking for this paper. Per-paper extraction owns candidate-level
        # gene/variant normalization and HGNC alias caches; paper-level citation
        # normalization lives in PreparedPaperContent upstream.
        self.candidate_meta = {}
        self.dropped_candidates = []
        self.strict_gate_drops = []
        self.evidence_gate_drops = []
        self.detail_extraction_status = "not_started"
        self.detail_extraction_error = ""
        self.detail_extraction_rows = 0
        self.associations = []
        self._candidate_terms_cache = {}
        self._citation_paper_text_cache = self.prepared_content.citation_text_normalized

        # Step 0.5: Abstract gene discovery (independent pass, catches natural-language gene refs)
        # e.g. abstract says "IL-6" / "IFN-γ" while full text says "interleukin-6" / "interferon-gamma"
        if getattr(config, "ENABLE_ABSTRACT_GENE_DISCOVERY", True) and self.abstract_text:
            logging.info("Step 0.5: Extracting gene-variant associations from abstract")
            t0 = time.time()
            with pipeline_tracer.stage("abstract_pass"):
                abstract_associations = self.extract_gene_names_from_abstract()
            if abstract_associations:
                added = self._ingest_associations(abstract_associations, "llm_abstract")
                logging.info(f"Abstract gene discovery added {added} candidate genes")
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                pipeline_tracer.capture(
                    "abstract_pass",
                    pmid=self.pmid,
                    inputs={
                        "abstract_length": len(self.abstract_text or ""),
                        "abstract_preview": pipeline_tracer.summarise(self.abstract_text or ""),
                    },
                    outputs={
                        "associations": pipeline_tracer.summarise(abstract_associations or []),
                        "candidate_count_after": len(self.candidate_meta),
                    },
                    duration_ms=(time.time() - t0) * 1000.0,
                )

        # Step 1: Optional LLM gene discovery on full paper text. Free-tier
        # defaults keep this off and rely on PubTator + deterministic seeding,
        # saving the quota for the detail-extraction call that creates output.
        if getattr(config, "ENABLE_LLM_GENE_DISCOVERY", False):
            logging.info("Step 1: Extracting gene-variant associations from paper text (pass 1)")
            t0 = time.time()
            with pipeline_tracer.stage("fulltext_pass_greedy"):
                self.extract_gene_names()
            pass1_count = len(self.associations)
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                pipeline_tracer.capture(
                    "fulltext_pass_greedy",
                    pmid=self.pmid,
                    inputs={
                        "paper_text_length": len(self.paper_text or ""),
                        "pubtator_seeds": self.pubtator_genes[:20],
                    },
                    outputs={
                        "associations_count_after_ingest": pass1_count,
                        "candidate_meta_size": len(self.candidate_meta),
                    },
                    duration_ms=(time.time() - t0) * 1000.0,
                )
        else:
            pass1_count = len(self.associations)
            logging.info(
                "Step 1: Skipping optional full-text Gemini gene discovery "
                "(ENABLE_LLM_GENE_DISCOVERY=false)"
            )

        # Step 1b: Second independent LLM pass at a higher temperature to actually diverge from
        # pass 1. temperature=0 (greedy) is nominally deterministic but Gemini's inference is not
        # bit-reproducible; in practice two greedy passes often return identical token sequences.
        # Running at temperature=0.4 forces the model to sample from different completions and
        # recover genes that the greedy pass missed (e.g. cytokines in a primarily cardiac paper).
        if getattr(config, "ENABLE_LLM_GENE_DISCOVERY", False) and getattr(
            config, "ENABLE_SECOND_GENE_DISCOVERY_PASS", False
        ):
            logging.info(
                "Step 1b: Second gene discovery pass (temperature=0.4) for recall improvement"
            )
            try:
                t0 = time.time()
                with pipeline_tracer.stage("fulltext_pass_recall"):
                    self.extract_gene_names(temperature=0.4)
                pass2_count = len(self.associations)
                if pass2_count > pass1_count:
                    logging.info(
                        f"Second pass added {pass2_count - pass1_count} additional genes (total: {pass2_count})"
                    )
                if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                    pipeline_tracer.capture(
                        "fulltext_pass_recall",
                        pmid=self.pmid,
                        inputs={"temperature": 0.4},
                        outputs={
                            "pass1_count": pass1_count,
                            "pass2_count": pass2_count,
                            "new_from_recall": pass2_count - pass1_count,
                        },
                        duration_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception as e:
                logging.warning(
                    f"Second gene discovery pass failed, continuing with pass-1 results: {e}"
                )
        else:
            logging.info("Step 1b: Skipping second Gemini gene discovery pass")

        # Step 1.1: Deterministic lexicon candidates (HGNC symbols/aliases)
        t0 = time.time()
        with pipeline_tracer.stage("deterministic_scan"):
            deterministic_candidates = self.extract_deterministic_candidates()
        if deterministic_candidates:
            added = self._ingest_associations(deterministic_candidates, "deterministic_lexicon")
            logging.info(f"Deterministic candidate extraction added {added} genes")
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            pipeline_tracer.capture(
                "deterministic_scan",
                pmid=self.pmid,
                inputs={"paper_text_length": len(self.paper_text or "")},
                outputs={
                    "deterministic_hits": [a.get("gene") for a in (deterministic_candidates or [])],
                    "new_candidates_added": len(deterministic_candidates or []),
                    "candidate_meta_size": len(self.candidate_meta),
                },
                duration_ms=(time.time() - t0) * 1000.0,
            )

        # Step 1.25: Multimodal figure analysis (PMC figure images + captions)
        if getattr(config, "ENABLE_FIGURE_ANALYSIS", True) and self.figure_inputs:
            logging.info("Step 1.25: Extracting gene-variant associations from figures")
            t0 = time.time()
            with pipeline_tracer.stage("figure_analysis"):
                figure_associations = self.extract_gene_names_from_figures()
            if figure_associations:
                added = self._ingest_associations(figure_associations, "llm_figure")
                logging.info(f"Merged {added} figure-derived associations")
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                pipeline_tracer.capture(
                    "figure_analysis",
                    pmid=self.pmid,
                    inputs={"figures_available": len(self.figure_inputs)},
                    outputs={
                        "associations": pipeline_tracer.summarise(figure_associations or []),
                    },
                    duration_ms=(time.time() - t0) * 1000.0,
                )

        # Step 1.5: HYBRID PIPELINE - Merge PubTator genes (ensures union)
        if self.pubtator_genes:
            with pipeline_tracer.stage("pubtator_merge"):
                pre_merge_size = len(self.candidate_meta)
                pt_associations = [{"gene": g, "variant": ""} for g in self.pubtator_genes if g]
                added_count = self._ingest_associations(pt_associations, "pubtator")
            if added_count > 0:
                logging.info(
                    f"Hybrid pipeline: Added {added_count} PubTator genes missed by Gemini"
                )
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                pipeline_tracer.capture(
                    "pubtator_merge",
                    pmid=self.pmid,
                    inputs={"pubtator_genes_count": len(self.pubtator_genes)},
                    outputs={
                        "new_from_pubtator": added_count,
                        "pre_merge_candidate_count": pre_merge_size,
                        "post_merge_candidate_count": len(self.candidate_meta),
                    },
                )

        # Final candidate_meta snapshot after all sourcing
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            pipeline_tracer.capture(
                "candidate_meta",
                pmid=self.pmid,
                outputs={
                    "total_candidates": len(self.candidate_meta),
                    "by_source": self._summarise_sources(),
                    "sample": pipeline_tracer.summarise(
                        [
                            {
                                "gene": v.get("gene"),
                                "variant": v.get("variant"),
                                "sources": self._as_sorted_strings(v.get("sources")),
                            }
                            for v in list(self.candidate_meta.values())[:30]
                        ]
                    ),
                },
            )

    def _run_grounding_check(self) -> None:
        """Step 1.6: Drop candidates not found in the fetched paper text.

        Flash sometimes hallucinates gene names it associates with the disease topic
        (e.g., cytokines for MIS-C papers) even when those genes are absent from the
        fetched text. The check uses: canonical symbol + HGNC aliases + raw_gene_labels
        (the exact string the LLM extracted, e.g. "BNP" for NPPB) to maximise recall
        while rejecting genuine hallucinations.

        Scope note: verifies gene presence only. Variant presence is validated later
        by the citation validator (Section 15.2) and the evidence gate (Section 15.3)
        — see F8c in docs/audit/final-audit.md for why the function's name is narrower than it
        appears.
        """
        if not (getattr(config, "ENABLE_GROUNDING_CHECK", True) and self.paper_text):
            return

        logging.info(
            "Step 1.6: Grounding check — verifying candidates are present in paper text"
        )
        grounded = []
        ungrounded_count = 0
        rescued_count = 0
        for assoc in self.associations:
            gene = (assoc.get("gene") or "").strip()
            variant = self._normalize_variant_value(assoc.get("variant", ""))
            if not gene:
                continue
            key = self._assoc_key(gene, variant)
            meta = self.candidate_meta.get(key) or {}
            sources = self._as_string_set(meta.get("sources"))
            if sources == {"llm_figure"}:
                # Verify gene appears in at least one figure caption or label.
                # This is a lighter check than prose grounding — we're confirming
                # the gene was actually visible in the figures, not hallucinated.
                figure_text_lower = " ".join(
                    f"{fig.get('label', '')} {fig.get('caption', '')}"
                    for fig in (self.figure_inputs or [])
                ).lower()
                candidate_terms = [gene] + list(
                    self._as_string_set(meta.get("raw_gene_labels"))
                )
                gene_in_figures = any(
                    term.lower() in figure_text_lower for term in candidate_terms if term
                )
                if gene_in_figures:
                    logging.debug(
                        f"Grounding check: passing '{gene}' (llm_figure — found in figure text)"
                    )
                    grounded.append(assoc)
                else:
                    logging.warning(
                        f"Grounding check: dropping '{gene}' (llm_figure — not found in any figure caption/label)"
                    )
                    if key in self.candidate_meta:
                        self.candidate_meta[key]["validation_outcome"] = "rejected_ungrounded_figure"
                    ungrounded_count += 1
                continue
            # Standard terms: canonical symbol + HGNC aliases
            terms = list(self._candidate_terms_for_row(gene, variant))
            # Also include the raw labels extracted by the LLM (e.g. "BNP" for NPPB,
            # "M-CSF" for CSF1) so normalization doesn't cause false grounding failures.
            for raw_label in self._as_string_set(meta.get("raw_gene_labels")):
                if raw_label and raw_label.upper() not in {t.upper() for t in terms}:
                    terms.append(raw_label)
            if self._find_evidence_snippet(terms):
                grounded.append(assoc)
            else:
                # Primary (truncated) search failed.
                # F8a: retry against untruncated text when truncation fired.
                # Invariant: self.paper_text is only reassigned by
                # _validate_and_prepare_paper_text on actual truncation (~line 2584),
                # so the identity check reliably gates the rescue branch.
                if (self.original_paper_text
                        and self.paper_text != self.original_paper_text):
                    rescue_snippet = self._find_evidence_snippet(
                        terms, text=self.original_paper_text
                    )
                    if rescue_snippet:
                        if key in self.candidate_meta:
                            self.candidate_meta[key]["truncation_rescued"] = True
                            self.candidate_meta[key]["validation_outcome"] = (
                                "passed_untruncated_rescue"
                            )
                        self._truncation_rescue_count += 1
                        rescued_count += 1
                        logging.info(
                            f"Grounding rescue: '{gene}' found in untruncated text only "
                            f"(truncation dropped a section containing this gene)."
                        )
                        grounded.append(assoc)
                        continue
                logging.warning(
                    f"Grounding check: dropping '{gene}' "
                    f"(raw: {self._as_sorted_strings(meta.get('raw_gene_labels'))}) "
                    f"— not found in paper text by any of {terms[:6]}"
                )
                # Mark in meta so the debug artifact records why this candidate was removed
                if key in self.candidate_meta:
                    self.candidate_meta[key]["validation_outcome"] = "rejected_ungrounded"
                ungrounded_count += 1
        if ungrounded_count:
            logging.info(
                f"Grounding check removed {ungrounded_count}/{len(self.associations)} ungrounded candidates"
            )
        self.associations = grounded

        # ── Tracer: grounding outcome
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            dropped_here = [
                {"gene": v.get("gene"), "variant": v.get("variant"),
                 "outcome": v.get("validation_outcome"),
                 "sources": self._as_sorted_strings(v.get("sources"))}
                for v in self.candidate_meta.values()
                if v.get("validation_outcome") in ("rejected_ungrounded", "rejected_ungrounded_figure")
            ]
            pipeline_tracer.capture(
                "grounding_check",
                pmid=self.pmid,
                inputs={"candidates_in": len(grounded) + ungrounded_count},
                outputs={
                    "grounded_count": len(grounded),
                    "dropped_count": ungrounded_count,
                    "rescued_count": rescued_count,
                    "dropped_samples": pipeline_tracer.summarise(dropped_here),
                },
            )

    def _run_validation_and_normalize(self) -> None:
        """Step 2: Gene validation heuristics + ensure one gene-level row per gene."""
        pre_validation_associations = list(self.associations)

        # Step 2: Apply heuristics to validate extracted genes
        logging.info("Step 2: Validating extracted genes against known databases")
        self._apply_gene_validation_heuristics()

        if (
            not self.associations
            and pre_validation_associations
            and getattr(config, "ENABLE_LLM_GENE_DISCOVERY_RESCUE", True)
            and not getattr(config, "ENABLE_LLM_GENE_DISCOVERY", False)
        ):
            deterministic_drops = [
                d
                for d in (self.dropped_candidates or [])
                if d.get("reason") == "deterministic_uncorroborated"
            ]
            if deterministic_drops and self._can_make_gemini_call(
                "rescue gene discovery", optional=True
            ):
                logging.info(
                    "No deterministic-only genes survived corroboration; "
                    "running one Gemini gene-discovery rescue pass"
                )
                rescue_before = len(self.associations)
                self.extract_gene_names()
                if (
                    getattr(config, "ENABLE_LLM_GENE_DISCOVERY_RESCUE_RECALL_PASS", True)
                    and self._can_make_gemini_call("rescue recall gene discovery", optional=True)
                ):
                    self.extract_gene_names(temperature=0.4)
                if len(self.associations) > rescue_before:
                    self._run_grounding_check()
                    self._apply_gene_validation_heuristics()

        # Reliability fallback: keep pre-validation candidates only when strict gate is disabled.
        if not self.associations and pre_validation_associations:
            if getattr(config, "ENABLE_STRICT_VALIDATION_GATE", True):
                logging.warning(
                    "Validation filtered out all associations; strict gate enabled, keeping result empty"
                )
            else:
                logging.warning(
                    "Validation filtered out all associations; strict gate disabled, falling back to pre-validation associations"
                )
                self.associations = pre_validation_associations

        # Ensure we have a single gene-level association (variant empty) per gene before LLM
        try:
            existing_pairs = set()
            genes_present = set()
            normalized: List[Dict[str, str]] = []
            for assoc in self.associations:
                if isinstance(assoc, dict):
                    g = (assoc.get("gene") or "").strip()
                    v = assoc.get("variant") or ""
                else:
                    g, v = assoc
                g_up = g.strip().upper()
                v_norm = (v or "").strip()
                if isinstance(v_norm, str) and v_norm.upper() in {"N/A", "NA", "NONE"}:
                    v_norm = ""
                existing_pairs.add((g_up, v_norm))
                genes_present.add(g_up)
                normalized.append({"gene": g, "variant": v_norm})

            for g_up in genes_present:
                if (g_up, "") not in existing_pairs:
                    normalized.append({"gene": g_up, "variant": ""})

            self.associations = normalized
        except Exception as e:
            logging.debug(f"Failed to ensure gene-level associations: {e}")

    def _run_detail_extraction(
        self, column_descriptions: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Step 3: Detail extraction + merge + fallback + evidence backfill.

        Returns the extracted_info list (may be empty).
        """
        logging.info("Step 3: Extracting detailed information for validated associations")
        _t0 = time.time()
        _assoc_count_in = len(self.associations)
        extracted_info = self.extract_gene_info(column_descriptions)

        # Merge duplicate rows: Stage 3 sometimes emits the same gene twice with different
        # fields filled (e.g. one row has Disease Association, another has Statistical Evidence).
        # Consolidate into one row per (gene_name, variant_name).
        if extracted_info and len(extracted_info) > 1:
            with pipeline_tracer.stage("row_merge"):
                extracted_info = self._merge_duplicate_gene_rows(extracted_info, column_descriptions)

        if not extracted_info and self.associations:
            logging.warning(
                "Detailed extraction returned no rows; emitting association-only fallback rows"
            )
            self.detail_extraction_status = "association_only_fallback_no_rows"
            # F11: same skeleton tag as the extract_gene_info fallback path —
            # downstream sees "this row has no LLM content".
            err_msg = str(getattr(self, "detail_extraction_error", "") or "")[:300]
            extracted_info = []
            for assoc in self.associations:
                gene = (
                    (assoc.get("gene") or "").strip()
                    if isinstance(assoc, dict)
                    else (assoc[0] or "").strip()
                )
                variant = (
                    self._normalize_variant_value(assoc.get("variant", ""))
                    if isinstance(assoc, dict)
                    else self._normalize_variant_value(assoc[1] if len(assoc) > 1 else "")
                )
                if not gene:
                    continue
                row = {
                    "gene_name": gene,
                    "variant_name": variant,
                    "extraction_mode": "skeleton",
                    "detail_extraction_error": err_msg or "association_only_fallback_no_rows",
                }
                for col in column_descriptions:
                    row[col] = ""
                    row[f"{col} Citation"] = ""
                extracted_info.append(row)

        if extracted_info:
            self._fill_missing_requested_fields(extracted_info, column_descriptions)
            with pipeline_tracer.stage("evidence_backfill"):
                self._backfill_sparse_row_evidence(extracted_info, column_descriptions)

        # ── Tracer: detail extraction outcome
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            pipeline_tracer.capture(
                "detail_extraction",
                pmid=self.pmid,
                inputs={
                    "associations_in": _assoc_count_in,
                    "user_columns": list(column_descriptions.keys()),
                },
                outputs={
                    "rows_returned": len(extracted_info or []),
                    "sample": pipeline_tracer.summarise(extracted_info[:3] if extracted_info else []),
                    "status": self.detail_extraction_status,
                },
                duration_ms=(time.time() - _t0) * 1000.0,
            )
            with pipeline_tracer.stage("row_merge"):
                pipeline_tracer.capture(
                    "row_merge",
                    pmid=self.pmid,
                    outputs={"rows_after_merge": len(extracted_info or [])},
                )
            with pipeline_tracer.stage("evidence_backfill"):
                pipeline_tracer.capture(
                    "evidence_backfill",
                    pmid=self.pmid,
                    outputs={"rows_after_backfill": len(extracted_info or [])},
                )

        return extracted_info

    def _run_post_validation(
        self,
        df: pd.DataFrame,
        column_descriptions: Dict[str, str],
        context_validation: Dict[str, Any],
    ) -> pd.DataFrame:
        """Step 4: Add metadata, apply strict gate, citation validation, and evidence gate."""
        self._add_validation_metadata(df)
        self._add_candidate_provenance_metadata(df)

        with pipeline_tracer.stage("strict_gate"):
            if getattr(config, "ENABLE_STRICT_VALIDATION_GATE", True):
                min_final_conf = float(getattr(config, "FINAL_VALIDATION_MIN_CONFIDENCE", 0.7))
                if "validation_confidence" in df.columns:
                    before = len(df)
                    conf_mask = df["validation_confidence"].astype(float) >= min_final_conf
                    dropped_df = df[~conf_mask]
                    if not dropped_df.empty:
                        for _, row in dropped_df.iterrows():
                            row_dict = row.to_dict()
                            self.strict_gate_drops.append(
                                {
                                    "gene": str(row_dict.get("gene_name") or "").strip(),
                                    "variant": self._normalize_variant_value(
                                        row_dict.get("variant_name", "")
                                    ),
                                    "reason": "below_final_validation_threshold",
                                    "association_type": str(row_dict.get("Association Type") or ""),
                                    "association_group": str(row_dict.get("Association Group") or ""),
                                    "validation_confidence": row_dict.get("validation_confidence"),
                                    "threshold": min_final_conf,
                                }
                            )
                    df = df[conf_mask].reset_index(drop=True)
                    dropped = before - len(df)
                    if dropped > 0:
                        logging.warning(
                            f"Strict validation gate dropped {dropped}/{before} rows below confidence {min_final_conf:.2f}"
                        )
                else:
                    # Defensive default: if confidence metadata missing, don't emit untrusted rows.
                    logging.warning(
                        "Strict validation gate active but validation_confidence missing; dropping all rows"
                    )
                    for _, row in df.iterrows():
                        row_dict = row.to_dict()
                        self.strict_gate_drops.append(
                            {
                                "gene": str(row_dict.get("gene_name") or "").strip(),
                                "variant": self._normalize_variant_value(
                                    row_dict.get("variant_name", "")
                                ),
                                "reason": "missing_validation_confidence",
                                "association_type": str(row_dict.get("Association Type") or ""),
                                "association_group": str(row_dict.get("Association Group") or ""),
                            }
                        )
                    df = pd.DataFrame()

            # ── Tracer: strict gate outcome
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                pipeline_tracer.capture(
                    "strict_gate",
                    pmid=self.pmid,
                    outputs={
                        "rows_after": len(df),
                        "dropped_count": len(self.strict_gate_drops),
                        "threshold": float(getattr(config, "FINAL_VALIDATION_MIN_CONFIDENCE", 0.7)),
                        "dropped": pipeline_tracer.summarise(self.strict_gate_drops),
                    },
                )

        # Only add citation validation if enabled
        if not df.empty and config.ENABLE_CITATION_VALIDATION:
            with pipeline_tracer.stage("citation_validation"):
                self._add_citation_validation_metadata(df)
            if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
                valid_counts = {}
                for col in df.columns:
                    if col.endswith("_citation_valid"):
                        base = col[: -len("_citation_valid")]
                        try:
                            valid_counts[base] = int(df[col].fillna(False).astype(bool).sum())
                        except Exception:
                            continue
                pipeline_tracer.capture(
                    "citation_validation",
                    pmid=self.pmid,
                    outputs={
                        "rows": len(df),
                        "valid_counts_by_column": valid_counts,
                    },
                )

        rows_before_evidence = len(df)
        with pipeline_tracer.stage("evidence_gate"):
            df = self._apply_evidence_gate(df, column_descriptions)
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            pipeline_tracer.capture(
                "evidence_gate",
                pmid=self.pmid,
                outputs={
                    "rows_before": rows_before_evidence,
                    "rows_after": len(df),
                    "dropped_count": len(self.evidence_gate_drops),
                    "dropped": pipeline_tracer.summarise(self.evidence_gate_drops),
                },
            )

        if not df.empty:
            self._add_context_metadata(df, context_validation)
        return df

    def _apply_gene_validation_heuristics(self):
        """
        Apply heuristics to validate extracted gene-variant associations.

        Uses gene database validation to filter and improve accuracy.
        """
        if not self.associations:
            logging.warning("No associations to validate")
            return

        # Validate all associations
        self.validation_results = self.gene_validator.validate_associations(self.associations)

        min_confidence = float(getattr(config, "GENE_VALIDATION_MIN_CONFIDENCE", 0.5))
        kept_associations: List[Dict[str, str]] = []
        dropped: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str]] = set()

        for assoc, result in zip(self.associations, self.validation_results):
            if isinstance(assoc, dict):
                gene_raw = (assoc.get("gene") or "").strip()
                variant_raw = assoc.get("variant", "")
            else:
                gene_raw = str(assoc[0] if len(assoc) > 0 else "").strip()
                variant_raw = assoc[1] if len(assoc) > 1 else ""

            gene_norm, _ = self._normalize_gene_symbol(gene_raw)
            variant_norm = self._normalize_variant_value(variant_raw)
            key = self._assoc_key(gene_norm, variant_norm)

            # Persist validation/provenance status in candidate metadata
            if key in self.candidate_meta:
                self.candidate_meta[key]["validation_confidence"] = result.confidence_score
                self.candidate_meta[key]["validation_source"] = result.validation_source
                self.candidate_meta[key]["validation_outcome"] = (
                    "passed"
                    if result.confidence_score >= min_confidence
                    else "rejected_low_confidence"
                )
            else:
                self.candidate_meta[key] = {
                    "gene": gene_norm,
                    "variant": variant_norm,
                    "sources": set(["unknown"]),
                    "normalization_applied": "",
                    "raw_gene_labels": set([gene_raw]),
                    "validation_confidence": result.confidence_score,
                    "validation_source": result.validation_source,
                    "validation_outcome": "passed"
                    if result.confidence_score >= min_confidence
                    else "rejected_low_confidence",
                }

            gene_up = gene_norm.upper()
            variant_up = variant_norm.upper()
            if result.confidence_score < min_confidence:
                if key in self.candidate_meta:
                    self.candidate_meta[key]["validation_outcome"] = "rejected_low_confidence"
                dropped.append(
                    {
                        "gene": gene_norm,
                        "variant": variant_norm,
                        "reason": "low_confidence",
                        "confidence": result.confidence_score,
                    }
                )
                continue

            meta = self.candidate_meta.get(key)
            sources = self._as_string_set(meta.get("sources")) if meta else set()
            require_corroboration = bool(
                getattr(config, "DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY", True)
            )
            # PubTator is a high-precision NCBI NER system — treat it as a trusted source
            # equivalent to LLM text extraction for corroboration purposes.
            # Only pure deterministic-lexicon-only hits (no LLM or PubTator backing) need corroboration.
            trusted_sources = {"llm_text", "llm_figure", "llm_abstract", "pubtator"}
            is_uncorroborated_lexicon_only = bool(sources) and not (sources & trusted_sources)
            if require_corroboration and not variant_norm and is_uncorroborated_lexicon_only:
                rescue_enabled = bool(
                    getattr(config, "ENABLE_DETERMINISTIC_CONTEXT_RESCUE", True)
                )
                context_ok = False
                context_reason = ""
                context_snippet = ""
                if rescue_enabled:
                    with pipeline_tracer.stage("corroboration_gate"):
                        context_ok, context_reason, context_snippet = (
                            self._deterministic_gene_context_evidence(gene_norm, variant_norm)
                        )

                if context_ok:
                    if key in self.candidate_meta:
                        self.candidate_meta[key]["validation_outcome"] = (
                            "passed_deterministic_context"
                        )
                        self.candidate_meta[key]["deterministic_context_reason"] = (
                            context_reason
                        )
                        self.candidate_meta[key]["deterministic_context_snippet"] = (
                            context_snippet
                        )
                else:
                    if key in self.candidate_meta:
                        self.candidate_meta[key]["validation_outcome"] = (
                            "rejected_uncorroborated_deterministic"
                        )
                        self.candidate_meta[key]["deterministic_context_reason"] = (
                            context_reason
                        )
                        self.candidate_meta[key]["deterministic_context_snippet"] = (
                            context_snippet
                        )
                    dropped.append(
                        {
                            "gene": gene_norm,
                            "variant": variant_norm,
                            "reason": "deterministic_uncorroborated",
                            "confidence": result.confidence_score,
                            "context_reason": context_reason,
                        }
                    )
                    continue

            if key in self.candidate_meta:
                if self.candidate_meta[key].get("validation_outcome") != (
                    "passed_deterministic_context"
                ):
                    self.candidate_meta[key]["validation_outcome"] = "passed"

            dedup_key = (gene_up, variant_up)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            kept_associations.append({"gene": gene_norm, "variant": variant_norm})

        self.validated_associations = kept_associations
        self.dropped_candidates = dropped
        self._refresh_all_candidate_caches()

        total_associations = len(self.associations)
        validated_count = len(self.validated_associations)
        validation_rate = validated_count / total_associations if total_associations > 0 else 0
        logging.info(
            f"Gene validation: {validated_count}/{total_associations} associations passed validation ({validation_rate:.1%})"
        )
        if dropped:
            logging.info(f"Gene validation dropped {len(dropped)} associations")
            for item in dropped[:5]:
                logging.info(
                    f"  - dropped {item['gene']} ({item['variant'] or 'gene-only'}): "
                    f"{item['reason']} (confidence={item['confidence']:.2f})"
                )

        self.associations = self.validated_associations

        # ── Tracer: split drops by reason for the three sub-gates (HGNC / low-conf / corroboration)
        if pipeline_tracer.is_enabled() and pipeline_tracer.matches(self.pmid):
            low_conf = [d for d in dropped if d.get("reason") == "low_confidence"]
            corrob = [d for d in dropped if d.get("reason") == "deterministic_uncorroborated"]
            pipeline_tracer.capture(
                "hgnc_validation",
                pmid=self.pmid,
                inputs={"associations_in": total_associations},
                outputs={
                    "results_sample": pipeline_tracer.summarise(
                        [
                            {"gene": r.gene, "variant": r.variant,
                             "confidence": r.confidence_score,
                             "source": r.validation_source,
                             "is_valid_gene": r.is_valid_gene}
                            for r in self.validation_results[:30]
                        ]
                    ),
                },
            )
            with pipeline_tracer.stage("low_confidence_gate"):
                pipeline_tracer.capture(
                    "low_confidence_gate",
                    pmid=self.pmid,
                    outputs={
                        "dropped_count": len(low_conf),
                        "dropped": pipeline_tracer.summarise(low_conf),
                        "threshold": min_confidence,
                    },
                )
            with pipeline_tracer.stage("corroboration_gate"):
                pipeline_tracer.capture(
                    "corroboration_gate",
                    pmid=self.pmid,
                    outputs={
                        "dropped_count": len(corrob),
                        "dropped": pipeline_tracer.summarise(corrob),
                        "survivors": validated_count,
                    },
                )


Stage5Pipeline = PaperAnalysisPipeline
