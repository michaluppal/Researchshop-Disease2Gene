import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import requests

from . import config, pipeline_tracer
from .gene_validator import (
    ContextWindowValidator,
    GeneValidator,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s"
)

# ---------------------------------------------------------------------------
# Prompt instruction constants — extracted verbatim from methods for readability.
# Dynamic parts (paper text, PubTator genes, column descriptions) are injected
# at the call site. Do NOT change wording without evaluating hallucination impact.
# ---------------------------------------------------------------------------

_GENE_DISCOVERY_INSTRUCTION_ABSTRACT = (
    "You are a biomedical gene extraction assistant. "
    "Extract ALL genes, cytokines, chemokines, interleukins, and gene products mentioned in this abstract. "
    "Focus on HUMAN genes. Do not extract genes from model organisms (mouse, rat, "
    "zebrafish) unless the paper explicitly maps them to human orthologs. "
    "Use official HGNC gene symbols (e.g. IL6 not interleukin-6, IFNG not interferon-gamma, CXCL9 not chemokine ligand 9, CSF1 not M-CSF). "
    "Include the specific variant (HGVS notation, rsID, etc.) if one is mentioned alongside the gene. "
    "If no specific variant is mentioned for a gene, use an empty string for variant. "
    "Only extract genes that are ACTUALLY mentioned in the text. Do NOT hallucinate or invent genes. "
    "CRITICAL DISAMBIGUATION: Only extract genes that the paper studies at the molecular or genetic level "
    "(e.g., gene expression, polymorphisms/variants, mutations, protein interactions, signaling pathways, gene regulation). "
    "Do NOT extract abbreviations that are used solely as clinical laboratory measurements or diagnostic test results "
    "(e.g., 'ESR 78 mm/h' is a lab value, not the ESR1 gene; 'AST 120 U/L' is a liver function test, not the GOT1 gene; "
    "'CRP 45 mg/L' is an inflammatory marker measurement, not the CRP gene). "
    "If a paper discusses both the clinical measurement AND the gene/protein at a molecular level, "
    "only extract it as a gene if the paper explicitly discusses it at the molecular level "
    "(e.g., gene expression, genetic variants, mRNA/protein levels, polymorphisms, pathway involvement)."
)

_GENE_DISCOVERY_INSTRUCTION_FULLTEXT = (
    "You are a biomedical gene extraction assistant. "
    "Extract ALL genes, cytokines, chemokines, interleukins, growth factors, receptors, and gene products mentioned in this paper. "
    "Use official HGNC gene symbols (e.g. IL6 not interleukin-6, IFNG not interferon-gamma, CXCL9 not chemokine ligand 9, CSF1 not M-CSF, IL17A not IL-17A). "
    "Include the specific variant (HGVS notation, rsID, etc.) if one is mentioned alongside the gene. "
    "If no specific variant is mentioned for a gene, use an empty string for variant. "
    "Only extract genes that are ACTUALLY discussed in the paper text. Do NOT hallucinate or invent genes that are not in the text. "
    "CRITICAL DISAMBIGUATION: Only extract genes that the paper studies at the molecular or genetic level "
    "(e.g., gene expression, polymorphisms/variants, mutations, protein interactions, signaling pathways, gene regulation). "
    "Do NOT extract abbreviations that are used solely as clinical laboratory measurements or diagnostic test results "
    "(e.g., 'ESR 78 mm/h' is a lab value, not the ESR1 gene; 'AST 120 U/L' is a liver function test, not the GOT1 gene; "
    "'CRP 45 mg/L' is an inflammatory marker measurement, not the CRP gene). "
    "If a paper discusses both the clinical measurement AND the gene/protein at a molecular level, "
    "only extract it as a gene if the paper explicitly discusses it at the molecular level "
    "(e.g., gene expression, genetic variants, mRNA/protein levels, polymorphisms, pathway involvement)."
)

_FIGURE_ANALYSIS_INSTRUCTION = (
    "You are analyzing a biomedical research figure. "
    "Extract gene symbols and specific variants that are explicitly visible in the figure text, "
    "axes labels, legends, annotations, or caption context. "
    "Use official HGNC gene symbols when possible. "
    "If no variant is shown, return an empty string for variant. "
    "Do not guess genes that are not explicitly shown."
)

_DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS = (
    "\n\nCRITICAL INSTRUCTIONS:"
    "\n- For gene_name and variant_name: Use exactly the values provided in Associations JSON."
    '\n- If variant_name is empty in Associations JSON, keep variant_name as empty string "".'
    "\n- Each gene is INDEPENDENT. You MUST fill in values for EVERY gene in the list, even if multiple genes appear together in the paper. Do NOT leave gene-level rows empty because another gene was already filled."
    "\n- Always include one gene-only row per gene (variant_name empty). Put gene-level facts specific to THAT gene in those rows."
    "\n- In variant rows (variant_name non-empty) for the same gene: provide only variant-specific details; if none, leave those variant rows empty."
    "\n- Do NOT repeat the same sentence across multiple VARIANT rows of the SAME gene. But across different genes, each gene gets its own independent facts even if the paper discusses them together."
    "\n- For any field that is filled, provide a separate '{Field} Citation' as a direct quote or page/section reference. Leave citation empty if the field is empty."
    "\n- Do NOT output placeholders like 'No supporting citation found in paper'. Use empty string instead."
    "\n- Format for gene_name and variant_name: Just the name (e.g., 'BRCA1' or 'rs123456')."
    "\n- Do NOT combine answers and citations in the same field."
    "\n- VERBATIM NUMBERS AND UNITS: Copy all numerical values and their units EXACTLY as written in the paper. Do NOT convert, round, or substitute units. For example: if the paper says '242 mg/L', write '242 mg/L' — never '242 mg/dl' or '0.242 g/L'. If the paper says 'p < 0.01', write 'p < 0.01' — not 'p=0.01'."
    "\n- NO ELLIPSIS IN CITATIONS: Citation fields must be verbatim excerpts from the paper — do NOT use '...', '[...]', or any other ellipsis or truncation. If the full sentence is too long, quote only the most specific relevant clause. If you cannot provide a verbatim quote, leave the citation field empty."
    "\n- CITATION SOURCE PRIORITY: Prefer citing prose sentences from Results/Discussion/Methods. If the ONLY textual support for a finding is in a table with no accompanying prose sentence, you MAY cite the table in this exact format: '[Table N] caption_text: relevant_cell_values' (e.g., '[Table 2] Gene expression in tumor samples: BRCA1 | p=0.001 | FC=2.5'). Never cite raw number sequences without table label and column context."
    "\n- GENE-NAMED CITATIONS: Every citation field must include at least one sentence that explicitly names the gene, its protein product, or one of its known aliases/abbreviations (e.g. 'BNP', 'NT-proBNP' for NPPB; 'PSA' for KLK3). If the most relevant sentence does not name the gene (e.g. it says 'heart injury markers' or 'the biomarker'), you may add AT MOST ONE immediately adjacent sentence — the sentence that directly precedes or directly follows it in the same paragraph with no section heading, subsection title, or paragraph break between them. Do NOT reach into Methods, definitions blocks, supplementary tables, or any other section to find the gene name. If no immediately adjacent sentence in the same paragraph names the gene, leave the citation field empty."
)


class GeneInfoPipeline:
    def __init__(
        self,
        paper_text: str,
        abstract_text: str = "",
        pubtator_genes: List[str] = None,
        figure_inputs: List[Dict[str, Any]] = None,
        table_inputs: List[Dict[str, Any]] = None,
        pmid: Optional[str] = None,
    ):
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in the configuration.")
        self.pmid = pmid  # used only for the pipeline tracer
        self.paper_text = paper_text
        self.abstract_text = abstract_text  # Store abstract separately
        self.original_paper_text = paper_text  # Keep original for reference
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

        # Hybrid pipeline: PubTator genes passed in from orchestrator
        self.pubtator_genes = pubtator_genes or []
        self.figure_inputs = figure_inputs or []
        self.table_inputs = table_inputs or []
        self._paper_api_calls: int = 0
        self._last_gemini_call_at: Optional[float] = None
        self._quota_limited: bool = False
        self._context_warning: Optional[str] = None
        self._truncation_rescue_count: int = 0

        # Lazy import to avoid top-level import failures
        from google import genai  # type: ignore

        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.gene_validator = GeneValidator()
        self.context_validator = ContextWindowValidator()

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        err = str(error)
        return "429" in err or "RESOURCE_EXHAUSTED" in err or "quota" in err.lower()

    @staticmethod
    def _extract_retry_delay_seconds(error: Exception) -> Optional[int]:
        err = str(error)
        delay_match = re.search(r"retryDelay[\"'\s:]+(\d+)s", err)
        if delay_match:
            return int(delay_match.group(1))
        return None

    def _can_make_gemini_call(self, purpose: str, *, optional: bool = False) -> bool:
        max_calls = int(getattr(config, "GEMINI_MAX_CALLS_PER_PAPER", 0) or 0)
        if max_calls <= 0 or self._paper_api_calls < max_calls:
            return True
        msg = (
            f"Gemini call budget reached for this paper "
            f"({self._paper_api_calls}/{max_calls}); skipping {purpose}"
        )
        if optional:
            logging.info(msg)
            return False
        raise RuntimeError(msg)

    def _generate_content_text(
        self,
        *,
        model_name: str,
        contents: list,
        generate_content_config: Any,
        purpose: str,
        optional: bool = False,
    ) -> str:
        """Call Gemini with per-paper budget and spacing guards."""
        if not self._can_make_gemini_call(purpose, optional=optional):
            return ""

        min_delay = float(getattr(config, "GEMINI_INTER_CALL_DELAY_SECONDS", 0) or 0)
        if self._last_gemini_call_at is not None and min_delay > 0:
            elapsed = time.time() - self._last_gemini_call_at
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed)

        self._paper_api_calls += 1
        self._last_gemini_call_at = time.time()
        full_response_text = ""
        try:
            for chunk in self.client.models.generate_content_stream(
                model=f"models/{model_name}",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    full_response_text += chunk.text
        except Exception as e:
            if self._is_rate_limit_error(e):
                self._quota_limited = True
            raise
        return full_response_text

    def _should_retry_gemini_error(self, error: Exception, attempt: int, max_retries: int) -> tuple[bool, int]:
        """Return (should_retry, wait_seconds) for Gemini failures."""
        if attempt >= max_retries - 1:
            return False, 0

        if not self._is_rate_limit_error(error):
            wait = 2 ** attempt
            return True, max(1, wait)

        suggested = self._extract_retry_delay_seconds(error)
        if suggested is None:
            return False, 0
        if not getattr(config, "GEMINI_RETRY_RATE_LIMIT_WITH_DELAY", True):
            return False, 0
        wait = min(
            int(suggested) + 3,
            int(getattr(config, "GEMINI_MAX_RATE_LIMIT_WAIT_SECONDS", 75)),
        )
        return True, max(wait, 1)

    @staticmethod
    def _normalize_variant_value(value: Any) -> str:
        """Normalize placeholder variant values to empty string."""
        text = str(value or "").strip()
        if text.upper() in {"N/A", "NA", "NONE", "NULL"}:
            return ""
        return text

    @staticmethod
    def _normalize_empty_placeholder(value: Any) -> str:
        """
        Normalize known empty/no-evidence placeholders to empty string.
        """
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        placeholders = {
            "no supporting citation found in paper",
            "no supporting citation found",
            "not found in paper",
            "not available",
            "n/a",
            "na",
            "none",
            "null",
            "no evidence",
            "insufficient evidence",
            "not reported",
        }
        if lowered in placeholders:
            return ""
        return text

    @staticmethod
    def _assoc_key(gene: str, variant: str) -> Tuple[str, str]:
        return ((gene or "").strip().upper(), (variant or "").strip().upper())

    def _row_has_user_evidence(
        self, row: Dict[str, Any], column_descriptions: Dict[str, str]
    ) -> bool:
        for col in column_descriptions:
            if str(row.get(col, "")).strip():
                return True
            citation_col = f"{col} Citation"
            if str(row.get(citation_col, "")).strip():
                return True
        return False

    def _count_user_evidence_cells(
        self, row: Dict[str, Any], column_descriptions: Dict[str, str]
    ) -> int:
        count = 0
        for col in column_descriptions:
            if str(row.get(col, "")).strip():
                count += 1
            citation_col = f"{col} Citation"
            if str(row.get(citation_col, "")).strip():
                count += 1
        return count

    def _get_hgnc_aliases_for_gene(self, gene: str) -> List[str]:
        """
        Return HGNC alias_symbol + prev_symbol entries for the given canonical gene symbol.
        Used by alias-aware evidence backfill to find genes referenced by natural language names.
        """
        db = getattr(self.gene_validator, "_local_gene_db", None) or {}
        if not db:
            return []
        gene_u = (gene or "").strip().upper()
        info = db.get(gene_u) or {}
        aliases = list(info.get("alias_symbol") or info.get("aliases") or [])
        prevs = list(info.get("prev_symbol") or info.get("prev_symbols") or [])
        all_terms = [str(a).strip() for a in aliases + prevs if str(a).strip()]
        # Cap at 15 to avoid exploding search with genes that have many aliases
        return all_terms[:15]

    def _candidate_terms_for_row(self, gene: str, variant: str) -> List[str]:
        """
        Build search terms for deterministic evidence backfill.
        """
        terms: List[str] = []
        if gene:
            terms.append(gene)

        key = self._assoc_key(gene, variant)
        meta = self.candidate_meta.get(key) or {}
        raw_labels = meta.get("raw_gene_labels", set())
        if isinstance(raw_labels, set):
            iterable = raw_labels
        elif isinstance(raw_labels, (list, tuple)):
            iterable = raw_labels
        elif isinstance(raw_labels, str):
            iterable = [raw_labels]
        else:
            iterable = []

        for raw in iterable:
            text = str(raw or "").strip()
            if text:
                terms.append(text)

        # Alias-aware backfill: also search HGNC aliases so natural language
        # names like "interleukin-6" are found when grounding IL6.
        for alias in self._get_hgnc_aliases_for_gene(gene):
            terms.append(alias)

        deduped: List[str] = []
        seen: Set[str] = set()
        for term in terms:
            marker = term.upper()
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(term)
        return deduped

    def _find_gene_specific_snippet(
        self,
        primary_terms: List[str],
        peer_entries: List[Tuple[str, Set[str]]],
    ) -> Tuple[str, bool, List[str]]:
        """
        Two-tier snippet search for evidence backfill (F12).

        Returns (snippet, is_gene_specific, co_mentioned_symbols).

        Phase 1 (gene-specific): walk re.finditer over each primary_term's
        word-boundary-guarded pattern. For each match, build the final snippet
        window (sentence-start trimmed + capped at EVIDENCE_SNIPPET_MAX_CHARS
        just like _find_evidence_snippet does). Check each peer term set against
        that FINAL window with the same (?<![A-Za-z0-9])...(?![A-Za-z0-9])
        word-boundary guards. Return the first match where no peer hit is found.
        Cap: examine at most EVIDENCE_BACKFILL_MAX_SCAN_MATCHES matches per
        primary term.

        Phase 2 (fallback): call self._find_evidence_snippet(primary_terms) to
        get the first-match snippet. Scan that snippet for peers. Return with
        is_gene_specific=False and the list of peer canonical symbols present.

        Empty peer_entries -> phase 1 always succeeds on the first match;
        return (snippet, True, []).

        peer_entries is a list of (canonical_symbol, term_set) tuples where
        term_set contains the canonical symbol plus any aliases. The explicit
        tuple avoids set-ordering issues when reporting co-mentioned symbols.

        If no primary match found at all -> return ("", False, []).
        """
        text = self.paper_text or ""
        if not text:
            return "", False, []

        max_chars = max(int(getattr(config, "EVIDENCE_SNIPPET_MAX_CHARS", 240)), 80)
        max_scan = max(
            int(getattr(config, "EVIDENCE_BACKFILL_MAX_SCAN_MATCHES", 50)), 1
        )

        def _build_snippet(match: re.Match) -> str:
            raw_start = max(0, match.start() - 80)
            boundary = re.search(r"(?<=[.!?])\s+", text[raw_start : match.start()])
            start = raw_start + boundary.end() if boundary else raw_start
            end = min(len(text), match.end() + 220)
            snippet = re.sub(r"\s+", " ", text[start:end]).strip()
            if len(snippet) > max_chars:
                snippet = snippet[: max_chars - 3].rstrip() + "..."
            return snippet

        def _peers_present_in(snippet: str) -> List[str]:
            present: List[str] = []
            if not snippet:
                return present
            for canonical, term_set in peer_entries:
                hit = False
                for peer_term in term_set:
                    peer_needle = str(peer_term or "").strip()
                    if not peer_needle:
                        continue
                    peer_pattern = (
                        rf"(?i)(?<![A-Za-z0-9]){re.escape(peer_needle)}(?![A-Za-z0-9])"
                    )
                    if re.search(peer_pattern, snippet):
                        hit = True
                        break
                if hit:
                    present.append(canonical)
            return present

        # Phase 1: gene-specific search.
        for term in primary_terms:
            needle = str(term or "").strip()
            if not needle:
                continue

            patterns = [rf"(?i)(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])"]
            alnum = re.sub(r"[^A-Za-z0-9]", "", needle)
            if len(alnum) >= 3:
                fuzzy = r"[\s\-_\/\.\(\)]*".join(re.escape(ch) for ch in alnum)
                patterns.append(rf"(?i)(?<![A-Za-z0-9]){fuzzy}(?![A-Za-z0-9])")

            for pattern in patterns:
                scanned = 0
                for match in re.finditer(pattern, text):
                    if scanned >= max_scan:
                        break
                    scanned += 1
                    snippet = _build_snippet(match)
                    if not snippet:
                        continue
                    if not peer_entries:
                        return snippet, True, []
                    peers_in_window = _peers_present_in(snippet)
                    if not peers_in_window:
                        return snippet, True, []

        # Phase 2: fallback to first-match snippet; flag as co-mention.
        fallback = self._find_evidence_snippet(primary_terms)
        if not fallback:
            return "", False, []
        co_mentioned = _peers_present_in(fallback)
        return fallback, False, co_mentioned

    def _find_evidence_snippet(
        self, terms: List[str], text: Optional[str] = None
    ) -> str:
        """
        Find the first grounded snippet in paper text mentioning any candidate term.

        When `text` is None (default), uses `self.paper_text` — preserves existing
        behaviour for all current callers. Passing `text=` explicitly lets callers
        (e.g. F8a truncation rescue) search an alternative corpus such as
        `self.original_paper_text`.
        """
        if text is None:
            text = self.paper_text or ""
        if not text:
            return ""

        max_chars = max(int(getattr(config, "EVIDENCE_SNIPPET_MAX_CHARS", 240)), 80)
        for term in terms:
            needle = str(term or "").strip()
            if not needle:
                continue

            patterns = [rf"(?i)(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])"]
            alnum = re.sub(r"[^A-Za-z0-9]", "", needle)
            if len(alnum) >= 3:
                fuzzy = r"[\s\-_\/\.\(\)]*".join(re.escape(ch) for ch in alnum)
                patterns.append(rf"(?i)(?<![A-Za-z0-9]){fuzzy}(?![A-Za-z0-9])")

            for pattern in patterns:
                match = re.search(pattern, text)
                if not match:
                    continue
                # Try to start at the nearest sentence boundary before the match
                # so snippets don't begin mid-sentence (e.g. "in, while highest...")
                raw_start = max(0, match.start() - 80)
                # Look for a sentence-ending punctuation followed by a space/newline
                boundary = re.search(r"(?<=[.!?])\s+", text[raw_start : match.start()])
                start = raw_start + boundary.end() if boundary else raw_start
                end = min(len(text), match.end() + 220)
                snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                if len(snippet) > max_chars:
                    snippet = snippet[: max_chars - 3].rstrip() + "..."
                return snippet

        return ""

    def _deterministic_gene_context_evidence(
        self, gene: str, variant: str = ""
    ) -> Tuple[bool, str, str]:
        """
        Decide whether a deterministic-only gene hit has enough paper context to
        survive the corroboration gate.

        This is intentionally stricter than ordinary grounding. A symbol simply
        appearing in full text is not enough; the surrounding sentence/window must
        look like biological result/pathway evidence, and not like a methods-only
        primer, antibody, strain, catalog, or ambiguous-abbreviation mention.
        """
        text = self.paper_text or ""
        if not text:
            return False, "no_paper_text", ""

        gene_upper = (gene or "").strip().upper()
        terms = self._candidate_terms_for_row(gene, variant)
        if not terms:
            return False, "no_candidate_terms", ""

        result_signal = re.compile(
            r"\b("
            r"significant(?:ly)?|differential(?:ly)?|up-?regulated|down-?regulated|"
            r"higher|lower|increased?|decreased?|reduced|elevated|enriched|"
            r"induced|suppressed|activated|inhibited|log2|fold(?:-|\s)?change|"
            r"p\s*[<=>]|q\s*[<=>]|fdr|adjusted\s+p"
            r")\b",
            re.IGNORECASE,
        )
        pathway_signal = re.compile(
            r"\b("
            r"pathways?|signaling|signal(?:ling)?|mediated\s+by|responses?|"
            r"interferon\s+response|immune\s+response|antiviral|transcriptomic|"
            r"gene\s+sets?|degs?|differentially\s+expressed\s+genes"
            r")\b",
            re.IGNORECASE,
        )
        weak_context = re.compile(
            r"\b("
            r"primers?|forward|reverse|qPCR\s+primer|RT-?qPCR|housekeeping|"
            r"reference\s+gene|antibod(?:y|ies)|clone|catalog|cat\.?\s*no|"
            r"supplier|manufacturer|dilution|reagents?|kit|buffer|"
            r"isotype|fluorochrome|plasmid|vector|transfection|"
            r"strain|isolate|orf\d*|genome|nucleotide|amino\s+acid\s+identity"
            r")\b",
            re.IGNORECASE,
        )
        molecular_signal = re.compile(
            r"\b(expression|expressed|mRNA|transcript|protein|cytokine|chemokine|receptor)\b",
            re.IGNORECASE,
        )

        def _term_patterns(term: str) -> List[str]:
            needle = str(term or "").strip()
            if not needle:
                return []
            patterns = [rf"(?i)(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])"]
            alnum = re.sub(r"[^A-Za-z0-9]", "", needle)
            if len(alnum) >= 3:
                fuzzy = r"[\s\-_\/\.\(\)]*".join(re.escape(ch) for ch in alnum)
                patterns.append(rf"(?i)(?<![A-Za-z0-9]){fuzzy}(?![A-Za-z0-9])")
            return patterns

        def _sentence_for_match(match: re.Match) -> str:
            left = max(
                text.rfind(".", 0, match.start()),
                text.rfind("!", 0, match.start()),
                text.rfind("?", 0, match.start()),
                text.rfind("\n", 0, match.start()),
            )
            start = left + 1 if left >= 0 else max(0, match.start() - 140)
            right_candidates = [
                pos for pos in (
                    text.find(".", match.end()),
                    text.find("!", match.end()),
                    text.find("?", match.end()),
                    text.find("\n", match.end()),
                )
                if pos >= 0
            ]
            end = min(right_candidates) + 1 if right_candidates else min(len(text), match.end() + 320)
            sentence = re.sub(r"\s+", " ", text[start:end]).strip()
            if len(sentence) > 500:
                sentence = sentence[:497].rstrip() + "..."
            return sentence

        def _window_for_match(match: re.Match) -> str:
            start = max(0, match.start() - 450)
            end = min(len(text), match.end() + 450)
            return re.sub(r"\s+", " ", text[start:end]).strip()

        rejection_snippet = ""
        max_scan = max(int(getattr(config, "EVIDENCE_BACKFILL_MAX_SCAN_MATCHES", 50)), 1)
        for term in terms:
            for pattern in _term_patterns(term):
                scanned = 0
                for match in re.finditer(pattern, text):
                    if scanned >= max_scan:
                        break
                    scanned += 1

                    sentence = _sentence_for_match(match)
                    window = _window_for_match(match)
                    combined = f"{sentence} {window}"
                    snippet = sentence or window[:500]
                    if not rejection_snippet:
                        rejection_snippet = snippet

                    if gene_upper == "PAM" and re.search(
                        r"\b(porcine\s+alveolar\s+macrophages?|primary\s+alveolar\s+macrophages?|"
                        r"pulmonary\s+intravascular\s+macrophages?|macrophages?|PAMs?|PIMs?)\b",
                        combined,
                        re.IGNORECASE,
                    ):
                        continue

                    if gene_upper == "GP5" and re.search(
                        r"\b(PRRSV|viral|virus|strain|isolate|ORF5|glycoprotein\s+5|genome)\b",
                        combined,
                        re.IGNORECASE,
                    ):
                        continue

                    has_weak = bool(weak_context.search(combined))
                    has_result = bool(result_signal.search(combined))
                    has_pathway = bool(pathway_signal.search(combined))
                    has_molecular = bool(molecular_signal.search(combined))

                    if has_weak and not (has_result or has_pathway):
                        continue
                    if has_result and (has_molecular or has_pathway):
                        return True, "result_context", snippet
                    if has_pathway:
                        return True, "pathway_context", snippet

        return False, "no_strong_deterministic_context", rejection_snippet

    def _merge_duplicate_gene_rows(
        self, rows: List[Dict[str, Any]], column_descriptions: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Merge rows that share the same (gene_name, variant_name).

        Stage 3 sometimes returns the same gene twice with different fields filled —
        e.g. one entry has Disease Association populated, another has Statistical Evidence.
        For each field we take the first non-empty value encountered.
        Row order is preserved (first occurrence of each gene determines position).
        """
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        order: List[Tuple[str, str]] = []

        all_data_cols = list(column_descriptions.keys()) + [
            f"{c} Citation" for c in column_descriptions
        ]

        for row in rows:
            gene = str(row.get("gene_name") or "").strip()
            variant = self._normalize_variant_value(row.get("variant_name", ""))
            key = (gene.upper(), variant.upper())

            if key not in merged:
                merged[key] = dict(row)
                order.append(key)
            else:
                existing = merged[key]
                for col in all_data_cols:
                    if not existing.get(col) and row.get(col):
                        existing[col] = row[col]

        merged_count = len(rows) - len(order)
        if merged_count > 0:
            logging.info(
                f"Merged {merged_count} duplicate Stage 3 row(s) into their parent gene entries"
            )
        return [merged[k] for k in order]

    def _backfill_sparse_row_evidence(
        self, extracted_info: List[Dict[str, Any]], column_descriptions: Dict[str, str]
    ):
        """
        For rows with zero extracted user evidence, backfill a grounded snippet.

        F12: prefer gene-specific sentences over co-mentions. Tag each backfilled
        row with evidence_specificity ('gene_specific' or 'co_mention') and
        co_mentioned_genes (semicolon-joined peer symbols if co_mention).
        """
        if not getattr(config, "ENABLE_EVIDENCE_BACKFILL", True):
            return
        if not extracted_info or not column_descriptions:
            return

        target_col = (
            "Key Finding"
            if "Key Finding" in column_descriptions
            else next(iter(column_descriptions))
        )
        target_citation_col = f"{target_col} Citation"

        # F12: Build peer-term lookup keyed by (gene_upper, variant_upper).
        # Each row's peer set is all OTHER rows' (canonical_symbol, term_set).
        # Using the identity key (not just gene) handles same-gene-multi-variant.
        all_row_keys: List[Tuple[str, str, str]] = []  # (gene_upper, var_upper, gene_original)
        for row in extracted_info:
            if not isinstance(row, dict):
                continue
            gene = str(row.get("gene_name") or "").strip()
            variant = self._normalize_variant_value(row.get("variant_name", ""))
            if not gene:
                continue
            all_row_keys.append((gene.upper(), variant.upper(), gene))

        # Precompute each row's term set once (for use as peer_term_set).
        term_set_by_key: Dict[Tuple[str, str], Tuple[str, Set[str]]] = {}
        for gene_u, var_u, gene_orig in all_row_keys:
            terms = self._candidate_terms_for_row(gene_orig, var_u)
            term_set_by_key[(gene_u, var_u)] = (gene_orig.upper(), set(terms))

        backfilled = 0
        for row in extracted_info:
            if not isinstance(row, dict):
                continue
            if self._row_has_user_evidence(row, column_descriptions):
                continue

            gene = str(row.get("gene_name") or "").strip()
            variant = self._normalize_variant_value(row.get("variant_name", ""))
            if not gene:
                continue
            gene_upper = gene.upper()

            # Build peer entries: rows for OTHER genes only.
            # Same-gene / different-variant rows are NOT peers — they annotate
            # the same gene, so a sentence mentioning that gene is equally valid
            # evidence for both rows. Exclude by gene (not by identity_key) to
            # avoid a row's own gene appearing in its peer set.
            peer_entries: List[Tuple[str, Set[str]]] = [
                entry
                for key, entry in term_set_by_key.items()
                if key[0] != gene_upper
            ]

            primary_terms = self._candidate_terms_for_row(gene, variant)
            snippet, is_specific, co_mentioned = self._find_gene_specific_snippet(
                primary_terms, peer_entries
            )
            if not snippet:
                continue

            row[target_col] = snippet
            row[target_citation_col] = "Auto snippet from paper text"
            # F11: Mark that this row's evidence was produced by keyword search,
            # not by Gemini reading the gene's context. _compute_row_confidence
            # reads this flag and downgrades the row's tier accordingly.
            row["evidence_backfilled"] = True
            row["evidence_specificity"] = (
                "gene_specific" if is_specific else "co_mention"
            )
            row["co_mentioned_genes"] = (
                ";".join(co_mentioned) if co_mentioned else ""
            )
            backfilled += 1

        if backfilled:
            logging.info(f"Evidence backfill populated {backfilled} sparse rows")

    def _find_statistical_snippet_for_gene(self, gene: str, variant: str = "") -> str:
        """Find a gene-grounded sentence that carries statistical/result language."""
        primary_terms = self._candidate_terms_for_row(gene, variant)
        if not primary_terms:
            return ""

        stat_pattern = re.compile(
            r"\b("
            r"significant(?:ly)?|differential(?:ly)?|upregulated|downregulated|"
            r"higher|lower|enriched|cut-?off|p\s*[<=>]|q\s*[<=>]|fdr|"
            r"fold|log2|adjusted|confidence interval|odds ratio|figure|table"
            r")\b",
            re.IGNORECASE,
        )

        best = ""
        for term in primary_terms:
            for match in re.finditer(re.escape(term), self.paper_text, flags=re.IGNORECASE):
                start = max(0, match.start() - 600)
                end = min(len(self.paper_text), match.end() + 600)
                window = self.paper_text[start:end]
                sentences = re.split(r"(?<=[.!?])\s+", window)
                for sentence in sentences:
                    if not re.search(re.escape(term), sentence, flags=re.IGNORECASE):
                        continue
                    if not stat_pattern.search(sentence):
                        continue
                    cleaned = " ".join(sentence.split())
                    if len(cleaned) < 20:
                        continue
                    if not best or len(cleaned) < len(best):
                        best = cleaned[:500]
            if best:
                return best
        return best

    def _fill_missing_requested_fields(
        self, extracted_info: List[Dict[str, Any]], column_descriptions: Dict[str, str]
    ) -> None:
        """Fill common partially-empty fields with grounded existing evidence.

        Gemini often fills Disease Association/Key Finding but leaves "Conclusion"
        blank when the paper lacks a literal conclusion sentence per gene. For
        researcher-facing output, a supported interpretation is more useful than
        an empty cell. Statistical Evidence gets a stricter text search so we do
        not turn every generic key finding into a fake statistic.
        """
        if not extracted_info or not column_descriptions:
            return

        for row in extracted_info:
            if not isinstance(row, dict):
                continue
            gene = str(row.get("gene_name") or "").strip()
            variant = self._normalize_variant_value(row.get("variant_name", ""))
            if not gene:
                continue

            for column in column_descriptions:
                if str(row.get(column, "") or "").strip():
                    continue

                lower_column = column.lower()
                citation_col = f"{column} Citation"

                if "statistical" in lower_column:
                    snippet = self._find_statistical_snippet_for_gene(gene, variant)
                    if snippet:
                        row[column] = snippet
                        row[citation_col] = snippet
                    continue

                if "conclusion" in lower_column:
                    for source_col in ("Key Finding", "Disease Association"):
                        value = str(row.get(source_col, "") or "").strip()
                        citation = str(row.get(f"{source_col} Citation", "") or "").strip()
                        if value:
                            row[column] = value
                            row[citation_col] = citation or value
                            break

    def _apply_evidence_gate(
        self, df: pd.DataFrame, column_descriptions: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Drop rows lacking any user-facing evidence fields/citations in strict mode.
        """
        if df.empty or not column_descriptions:
            return df
        if not getattr(config, "ENABLE_STRICT_EVIDENCE_GATE", True):
            return df

        # Read per-source thresholds once for the log message
        llm_thresh = int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT", "0"))
        det_thresh = int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC", "1"))
        mixed_thresh = int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS", "1"))

        keep_mask = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            # Per-source threshold: LLM rows carry inherent trust from translation
            key = self._assoc_key(
                str(row_dict.get("gene_name") or "").strip(),
                self._normalize_variant_value(row_dict.get("variant_name", "")),
            )
            meta = self.candidate_meta.get(key) or {}
            sources = meta.get("sources", set()) or set()
            llm_sources = {"llm_text", "llm_figure", "llm_abstract"}
            is_llm_sourced = bool(sources & llm_sources)
            det_only = bool(sources) and not (sources & llm_sources)

            if is_llm_sourced:
                min_cells = max(
                    int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT", "0")), 0
                )
            elif det_only:
                min_cells = max(
                    int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC", "1")), 0
                )
            else:
                min_cells = max(int(getattr(config, "EVIDENCE_MIN_NONEMPTY_CELLS", "1")), 0)

            evidence_cells = self._count_user_evidence_cells(row_dict, column_descriptions)
            keep = evidence_cells >= min_cells
            keep_mask.append(keep)
            if not keep:
                source_tier = (
                    "llm" if is_llm_sourced else ("deterministic" if det_only else "mixed")
                )
                self.evidence_gate_drops.append(
                    {
                        "gene": str(row_dict.get("gene_name") or "").strip(),
                        "variant": self._normalize_variant_value(row_dict.get("variant_name", "")),
                        "reason": "insufficient_user_evidence",
                        "evidence_cells": int(evidence_cells),
                        "source_tier": source_tier,
                        "min_required": int(min_cells),
                    }
                )

        before = len(df)
        filtered = df[keep_mask].reset_index(drop=True)
        dropped = before - len(filtered)
        if dropped > 0:
            logging.warning(
                f"Strict evidence gate dropped {dropped}/{before} rows "
                f"(per-source thresholds: LLM={llm_thresh}, Deterministic={det_thresh}, Mixed={mixed_thresh})"
            )
        return filtered

    def _collect_debug_artifact(self) -> Dict[str, Any]:
        """
        Build a serializable debug artifact describing candidate lifecycle and drops.
        """
        candidates: List[Dict[str, Any]] = []
        for meta in self.candidate_meta.values():
            src = meta.get("sources", set())
            if isinstance(src, set):
                sources = sorted(str(s) for s in src if s)
            elif isinstance(src, (list, tuple)):
                sources = sorted(str(s) for s in src if s)
            elif isinstance(src, str):
                sources = [src]
            else:
                sources = []

            raw = meta.get("raw_gene_labels", set())
            if isinstance(raw, set):
                raw_labels = sorted(str(r) for r in raw if r)
            elif isinstance(raw, (list, tuple)):
                raw_labels = sorted(str(r) for r in raw if r)
            elif isinstance(raw, str):
                raw_labels = [raw]
            else:
                raw_labels = []

            candidates.append(
                {
                    "gene": str(meta.get("gene") or ""),
                    "variant": self._normalize_variant_value(meta.get("variant", "")),
                    "sources": sources,
                    "raw_gene_labels": raw_labels,
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
                }
                for assoc in (self.associations or [])
            ],
        }

    def _format_table_summary_for_prompt(self) -> str:
        """Format structured tables as a compact prompt section for Gemini.

        Caps at TABLE_MAX_PER_PAPER tables, 20 rows per table to avoid context overflow.
        """
        parts = []
        for t in self.table_inputs[:getattr(config, 'TABLE_MAX_PER_PAPER', 20)]:
            label = t.get("label", "Table")
            caption = t.get("caption", "")
            headers = t.get("headers", [])
            rows = t.get("rows", [])[:20]
            header_str = " | ".join(headers) if headers else ""
            row_strs = [" | ".join(str(c) for c in r) for r in rows]
            table_block = f"[{label}] {caption}"
            if header_str:
                table_block += f"\n{header_str}"
            if row_strs:
                table_block += "\n" + "\n".join(row_strs)
            parts.append(table_block)
        return "\n\n".join(parts)

    def _normalize_gene_symbol(self, gene: str) -> Tuple[str, str]:
        """
        Normalize candidate labels to canonical HGNC symbols when resolvable.
        Returns (normalized_gene, normalization_note).
        """
        raw = (gene or "").strip()
        if not raw:
            return "", ""

        if getattr(config, "ENABLE_BIOMARKER_NORMALIZATION", True):
            resolved, source = self.gene_validator.resolve_gene_symbol(raw)
            if resolved:
                resolved_u = resolved.upper()
                if resolved_u != raw.upper():
                    return resolved_u, f"{raw}->{resolved_u} ({source})"
                return resolved_u, source

        return raw, ""

    def _ingest_associations(self, associations: List[Any], source: str) -> int:
        """
        Merge associations into candidate_meta while tracking provenance.
        """
        added = 0
        for assoc in associations or []:
            if isinstance(assoc, dict):
                gene_raw = (assoc.get("gene") or "").strip()
                variant_raw = assoc.get("variant", "")
            else:
                if not assoc:
                    continue
                gene_raw = str(assoc[0] if len(assoc) > 0 else "").strip()
                variant_raw = assoc[1] if len(assoc) > 1 else ""

            if not gene_raw:
                continue

            variant_norm = self._normalize_variant_value(variant_raw)
            gene_norm, norm_note = self._normalize_gene_symbol(gene_raw)
            if not gene_norm:
                continue

            key = self._assoc_key(gene_norm, variant_norm)
            entry = self.candidate_meta.get(key)
            if entry is None:
                entry = {
                    "gene": gene_norm,
                    "variant": variant_norm,
                    "sources": set(),
                    "normalization_applied": norm_note,
                    "raw_gene_labels": set([gene_raw]),
                }
                self.candidate_meta[key] = entry
                added += 1
            else:
                entry["raw_gene_labels"].add(gene_raw)
                if norm_note and not entry.get("normalization_applied"):
                    entry["normalization_applied"] = norm_note

            entry["sources"].add(source)

        self._refresh_associations_from_meta()
        return added

    def _refresh_associations_from_meta(self):
        self.associations = []
        for entry in self.candidate_meta.values():
            self.associations.append(
                {
                    "gene": entry.get("gene", ""),
                    "variant": self._normalize_variant_value(entry.get("variant", "")),
                }
            )

    def extract_deterministic_candidates(self) -> List[Dict[str, str]]:
        """
        Deterministically extract candidate genes via canonical HGNC symbol matching.

        Important: this path intentionally does NOT use alias/previous-symbol expansion.
        Alias collisions on clinical abbreviations (e.g., ESR, AST, CRT, DIC) create high
        false-positive rates in biomedical tables and labs. Alias resolution remains enabled
        for model/PubTator candidates through the normalization resolver.
        """
        if not getattr(config, "ENABLE_DETERMINISTIC_CANDIDATES", True):
            return []

        db = getattr(self.gene_validator, "_local_gene_db", {}) or {}
        if not db:
            return []

        text = self.paper_text or ""
        if not text:
            return []

        # Token strategy: canonical uppercase tokens with alnum/hyphen shape.
        token_candidates: List[str] = []
        seen_tokens: Set[str] = set()
        for token in re.findall(r"\b[A-Za-z][A-Za-z0-9\-]{1,20}\b", text):
            # Guardrail: avoid sentence-case common words driving alias collisions.
            if not (token.isupper() or any(ch.isdigit() for ch in token) or "-" in token):
                continue
            token_u = token.upper()
            if token_u in seen_tokens:
                continue
            seen_tokens.add(token_u)
            token_candidates.append(token_u)
        out: List[Dict[str, str]] = []
        seen: Set[str] = set()
        max_candidates = max(int(getattr(config, "DETERMINISTIC_MAX_CANDIDATES", 120)), 10)
        for token in token_candidates:
            gene_info = db.get(token)
            if not gene_info:
                continue
            canonical = str(gene_info.get("symbol") or token).upper()
            canonical_up = canonical.upper()
            if canonical_up in seen:
                continue
            seen.add(canonical_up)
            out.append({"gene": canonical, "variant": ""})
            if len(out) >= max_candidates:
                break
        return out

    def extract_gene_names_from_abstract(self, title: str = ""):
        """
        FIX #5 (Revised): Extract gene-variant associations from ABSTRACT ONLY.

        This saves 99%+ tokens compared to full-text extraction for gene discovery.
        Typical abstract: 200-300 tokens vs. full text: 50,000+ tokens.

        Args:
            title: Paper title (optional, helps with context)

        Returns:
            List of gene-variant associations found in abstract
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        if not self.abstract_text or len(self.abstract_text) < 50:
            logging.warning("Abstract too short or missing for gene extraction")
            return []

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]  # Flash model

        # Combine title + abstract for better context
        text_to_analyze = (
            f"Title: {title}\n\nAbstract: {self.abstract_text}" if title else self.abstract_text
        )

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                required=["associations"],
                properties={
                    "associations": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "gene": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Official HGNC gene symbol (e.g. IL6, CXCL9, BRCA1)",
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Specific variant if mentioned (e.g. rs1234, c.123A>G), or empty string if none",
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        instruction = _GENE_DISCOVERY_INSTRUCTION_ABSTRACT

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{instruction}\n\n{text_to_analyze}")],
            ),
        ]

        max_retries = max(1, int(getattr(config, "GEMINI_OPTIONAL_MAX_RETRIES", 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="abstract gene discovery",
                    optional=True,
                )
                if not full_response_text:
                    break

                response_json = json.loads(full_response_text)
                self.associations = response_json.get("associations", [])

                if self.associations:
                    logging.info(
                        f"Abstract gene discovery found {len(self.associations)} associations"
                    )
                else:
                    logging.info(
                        "Abstract gene discovery found no associations - skipping full-text analysis"
                    )

                break  # Success

            except Exception as e:
                logging.error(
                    f"Error during abstract gene extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    time.sleep(wait)
                else:
                    logging.error("Abstract gene extraction failed after all retries")
                    self.associations = []
                    break

        return self.associations

    def extract_gene_names(self, temperature: float = None):
        """
        Extract gene-variant associations from the paper text using Gemini AI.

        If PubTator genes were provided (hybrid pipeline), they are used as high-confidence
        seeds that the LLM should include and can find additional genes beyond.

        Args:
            temperature: Override sampling temperature. If None, uses config default.
                         Pass a non-zero value (e.g. 0.4) for a recall-boosting second pass
                         so the model explores different completions instead of repeating pass 1.
        """
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]
        effective_temperature = (
            temperature if temperature is not None else config.GEMINI_CONFIG["temperature"]
        )

        # Build instruction + paper text
        instruction = _GENE_DISCOVERY_INSTRUCTION_FULLTEXT

        if self.pubtator_genes:
            # Hybrid mode: PubTator found these genes with high confidence
            pt_genes_str = ", ".join(self.pubtator_genes[:20])  # Limit to avoid context overflow
            user_prompt = f"""{instruction}

The following genes have been identified with high confidence by PubTator NER: {pt_genes_str}
Make sure to include these genes in your output. Additionally, look for any other genes that PubTator may have missed.

Paper text:
{self.paper_text}"""
            logging.info(
                f"Hybrid mode: Seeding Gemini with {len(self.pubtator_genes)} PubTator genes"
            )
        else:
            user_prompt = f"{instruction}\n\nPaper text:\n{self.paper_text}"

        generate_content_config = types.GenerateContentConfig(
            temperature=effective_temperature,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                required=["associations"],
                properties={
                    "associations": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "gene": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Official HGNC gene symbol (e.g. IL6, CXCL9, BRCA1, TP53)",
                                ),
                                "variant": genai.types.Schema(
                                    type=genai.types.Type.STRING,
                                    description="Specific variant if mentioned (e.g. rs1234, c.123A>G), or empty string if none",
                                ),
                            },
                        ),
                    ),
                },
            ),
        )

        contents = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_prompt)]),
        ]

        max_retries = max(1, int(getattr(config, "GEMINI_OPTIONAL_MAX_RETRIES", 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="full-text gene discovery",
                    optional=True,
                )
                if not full_response_text:
                    break

                response_json = json.loads(full_response_text)
                parsed_associations = response_json.get("associations", [])
                if parsed_associations:
                    self._ingest_associations(parsed_associations, "llm_text")
                    break  # Success, exit retry loop

                # Empty association list is a known flaky model outcome; retry.
                if attempt < max_retries - 1:
                    logging.warning(
                        f"Gene extraction returned 0 associations (attempt {attempt + 1}/{max_retries}), retrying..."
                    )
                    time.sleep(2 ** attempt)
                    continue
                break

            except Exception as e:
                logging.error(
                    f"Error during gene-variant extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    logging.info(f"Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    logging.error("All retry attempts failed for gene-variant extraction")
                    self.associations = []
                    break

        return self.associations

    def _build_gemini_image_part(self, types_module, image_bytes: bytes, mime_type: str):
        """Construct a Gemini image Part with fallback for library-version differences."""
        try:
            return types_module.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        except Exception:
            try:
                blob = types_module.Blob(data=image_bytes, mime_type=mime_type)
                return types_module.Part(inline_data=blob)
            except Exception:
                return None

    def _resolve_pmc_cdn_url(self, figure: Dict[str, Any]) -> List[str]:
        """Resolve CDN blob URLs for a PMC figure by scraping the article HTML page.

        PMC migrated figure hosting to cdn.ncbi.nlm.nih.gov/pmc/blobs/{hash}/{pmcid}/{hash}/{file}.
        These hash-based paths cannot be derived from the JATS XML href alone — they require a
        single HTTP fetch of the article HTML page.  Returns a list of candidate CDN URLs
        that match the figure filename, or an empty list if resolution fails.
        """
        primary_url = figure.get("url") or ""
        # Extract the base filename from the primary URL (e.g. "nihms393293f1.jpg", "gr1_lrg.jpg")
        filename = primary_url.rstrip("/").split("/")[-1] if primary_url else ""
        if not filename:
            return []

        # Derive article page URL: strip trailing filename component to get article base
        # e.g. "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3465532/nihms393293f1.jpg"
        #   → "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3465532/"
        # Then map to pmc.ncbi.nlm.nih.gov (the HTML reader endpoint).
        article_base = primary_url[:primary_url.rfind("/") + 1] if "/" in primary_url else ""
        if not article_base:
            return []
        article_page = article_base.replace(
            "www.ncbi.nlm.nih.gov/pmc/articles/",
            "pmc.ncbi.nlm.nih.gov/articles/",
        )

        try:
            resp = requests.get(
                article_page,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0 (ResearchShop Figure Fetch)"},
            )
            if resp.status_code != 200:
                return []
            # Extract all cdn.ncbi.nlm.nih.gov/pmc/blobs URLs whose filename matches
            stem = re.escape(re.sub(r'\.[^.]+$', '', filename))  # strip extension for fuzzy match
            cdn_pattern = re.compile(
                r'https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"\'>\s]+'
            )
            all_cdn = cdn_pattern.findall(resp.text)
            # Prefer exact filename match, then stem match
            exact = [u for u in all_cdn if u.endswith("/" + filename)]
            if exact:
                return exact
            stem_matches = [u for u in all_cdn if re.search(r'/' + stem + r'[^/]*$', u)]
            return stem_matches
        except Exception:
            return []

    def _fetch_figure_image(self, figure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Download a figure image from candidate URLs with size and type safeguards.

        Falls back to CDN URL resolution if all pre-built candidates return non-200.
        PMC migrated figure hosting to cdn.ncbi.nlm.nih.gov/pmc/blobs/... which requires
        an HTML page scrape to resolve the hash-based path components.
        """
        candidates = list(figure.get("url_candidates") or [])
        primary_url = figure.get("url")
        if primary_url and primary_url not in candidates:
            candidates.insert(0, primary_url)
        if not candidates:
            return None

        max_bytes = max(getattr(config, "FIGURE_IMAGE_MAX_BYTES", 5 * 1024 * 1024), 100000)
        timeout = max(getattr(config, "REQUEST_TIMEOUT", 30), 10)
        headers = {
            "User-Agent": "Mozilla/5.0 (ResearchShop Figure Fetch)",
            "Accept": "image/*,*/*;q=0.8",
        }

        def _try_download(url: str) -> Optional[Dict[str, Any]]:
            try:
                response = requests.get(
                    url, timeout=timeout, stream=True, allow_redirects=True, headers=headers
                )
                if response.status_code != 200:
                    return None

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_bytes:
                    return None

                mime_type = (
                    (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                )
                if not mime_type.startswith("image/"):
                    return None

                chunks: List[bytes] = []
                total = 0
                too_large = False
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        too_large = True
                        break
                    chunks.append(chunk)

                if too_large:
                    return None

                payload = b"".join(chunks)
                if not payload:
                    return None

                return {"bytes": payload, "mime_type": mime_type, "url": url}
            except Exception:
                return None

        # Phase 1: try pre-built candidate URLs
        for url in candidates:
            result = _try_download(url)
            if result:
                return result

        # Phase 2: CDN URL resolution fallback — fetch article HTML and extract blob URLs
        cdn_candidates = self._resolve_pmc_cdn_url(figure)
        if cdn_candidates:
            logging.debug(
                f"Figure fetch: primary candidates failed; trying {len(cdn_candidates)} CDN URL(s)"
            )
        for url in cdn_candidates:
            result = _try_download(url)
            if result:
                logging.debug(f"Figure fetch: CDN fallback succeeded for {url}")
                return result

        return None

    def extract_gene_names_from_figures(self) -> List[Dict[str, str]]:
        """
        Use Gemini multimodal analysis to discover gene/variant mentions from figure images.
        """
        if not getattr(config, "ENABLE_FIGURE_ANALYSIS", True):
            return []
        if not self.figure_inputs:
            return []

        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]
        max_figures = max(getattr(config, "FIGURE_MAX_IMAGES_PER_PAPER", 3), 0)
        if max_figures == 0:
            return []

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                required=["associations"],
                properties={
                    "associations": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "gene": genai.types.Schema(type=genai.types.Type.STRING),
                                "variant": genai.types.Schema(type=genai.types.Type.STRING),
                            },
                        ),
                    ),
                },
            ),
        )

        discovered: List[Dict[str, str]] = []
        _fig_inter_call_delay = max(
            int(getattr(config, "FIGURE_INTER_CALL_DELAY_SECONDS", 4)), 0
        )
        for idx, figure in enumerate(self.figure_inputs[:max_figures], start=1):
            if idx > 1 and _fig_inter_call_delay > 0:
                # Small mandatory gap between figure vision calls: prevents back-to-back
                # calls from immediately re-saturating the per-minute sliding rate window.
                import time as _time_mod
                _time_mod.sleep(_fig_inter_call_delay)
            downloaded = self._fetch_figure_image(figure)
            if not downloaded:
                logging.debug(f"Figure analysis skipped for figure {idx}: could not download image")
                continue

            image_part = self._build_gemini_image_part(
                types, downloaded["bytes"], downloaded["mime_type"]
            )
            if image_part is None:
                logging.debug(
                    f"Figure analysis skipped for figure {idx}: unsupported image part creation"
                )
                continue

            label = (figure.get("label") or "").strip()
            caption = (figure.get("caption") or "").strip()
            prompt = (
                _FIGURE_ANALYSIS_INSTRUCTION
                + f"\n\nFigure label: {label or 'N/A'}"
                + f"\nFigure caption: {caption or 'N/A'}"
            )

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        image_part,
                    ],
                )
            ]

            fig_max_retries = max(1, int(getattr(config, "GEMINI_OPTIONAL_MAX_RETRIES", 1)))
            fig_success = False
            for fig_attempt in range(fig_max_retries):
                try:
                    full_response_text = self._generate_content_text(
                        model_name=model_name,
                        contents=contents,
                        generate_content_config=generate_content_config,
                        purpose=f"figure analysis {idx}",
                        optional=True,
                    )
                    if not full_response_text:
                        break

                    response_json = json.loads(full_response_text) if full_response_text else {}
                    associations = (
                        response_json.get("associations", []) if isinstance(response_json, dict) else []
                    )
                    for assoc in associations:
                        if not isinstance(assoc, dict):
                            continue
                        gene = (assoc.get("gene") or "").strip()
                        variant = (assoc.get("variant") or "").strip()
                        if not gene:
                            continue
                        discovered.append({"gene": gene, "variant": variant})
                    fig_success = True
                    break
                except Exception as e:
                    should_retry, wait = self._should_retry_gemini_error(
                        e, fig_attempt, fig_max_retries
                    )
                    if should_retry:
                        logging.info(
                            f"Figure analysis rate limited for figure {idx} "
                            f"(attempt {fig_attempt + 1}/{fig_max_retries}): "
                            f"waiting {wait}s before retry"
                        )
                        time.sleep(wait)
                    else:
                        logging.warning(f"Figure analysis failed for figure {idx}: {e}")
                        break
            if not fig_success:
                continue

        # De-duplicate gene/variant pairs
        deduped: List[Dict[str, str]] = []
        seen = set()
        for assoc in discovered:
            gene_norm = assoc["gene"].strip().upper()
            variant_norm = (assoc.get("variant") or "").strip()
            if variant_norm.upper() in {"N/A", "NA", "NONE"}:
                variant_norm = ""
            key = (gene_norm, variant_norm.upper())
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"gene": assoc["gene"], "variant": variant_norm})

        if deduped:
            logging.info(f"Figure analysis discovered {len(deduped)} unique gene associations")
        return deduped

    def extract_gene_info(self, column_descriptions):
        """
        Extract detailed info for identified gene-variant associations based on provided column descriptions.
        """
        if not self.associations:
            self.detail_extraction_status = "no_associations"
            self.detail_extraction_error = ""
            self.detail_extraction_rows = 0
            return []

        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        model_name = config.GEMINI_CONFIG["data_extraction_model"]

        properties = {
            "gene_name": genai.types.Schema(
                type=genai.types.Type.STRING, description="The name of the gene."
            )
        }
        properties["variant_name"] = genai.types.Schema(
            type=genai.types.Type.STRING, description="The associated variant, if any."
        )
        # Only require identifiers; user fields are optional so the model can omit generic, non-variant-specific text
        required = ["gene_name", "variant_name"]
        # For each user column, request both the value and a separate citation field (optional)
        for column, description in column_descriptions.items():
            # Value field (optional)
            properties[column] = genai.types.Schema(
                type=genai.types.Type.STRING, description=description
            )
            # Citation field (optional)
            citation_col = f"{column} Citation"
            properties[citation_col] = genai.types.Schema(
                type=genai.types.Type.STRING,
                description=f"Direct quote or section/page reference supporting {column}. Leave empty if no variant-specific evidence.",
            )

        generate_content_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.ARRAY,
                items=genai.types.Schema(
                    type=genai.types.Type.OBJECT,
                    required=required,
                    properties=properties,
                ),
            ),
        )

        normalized_associations = []
        for assoc in self.associations:
            gene = (assoc.get("gene") or "").strip()
            variant = self._normalize_variant_value(assoc.get("variant", ""))
            if not gene:
                continue
            normalized_associations.append({"gene_name": gene, "variant_name": variant})

        associations_json = json.dumps(normalized_associations, ensure_ascii=False)
        prompt_text = (
            "Based on the following research paper text, extract the requested information for the following gene-variant associations:\n\n"
            f"Associations JSON (authoritative input): {associations_json}\n\n"
            "IMPORTANT: For each piece of information you extract, provide a specific citation "
            "(quote or section/page reference) from the paper text that directly supports your answer. "
            "If supporting evidence is not present, leave both the value and citation empty.\n\n"
            "Information to extract for each association:\n"
        )
        prompt_text += "- gene_name: The name of the gene. (Use exactly the gene name from the associations above)\n"
        prompt_text += "- variant_name: The associated variant, if any. (Use exactly the variant name from the associations above)\n"
        for column, description in column_descriptions.items():
            lower_column = column.lower()
            extra_guidance = ""
            if "statistical" in lower_column or "evidence" in lower_column:
                extra_guidance = (
                    " Include qualitative statistical language when exact p-values are absent, "
                    "such as significantly upregulated/downregulated, differentially expressed, "
                    "not significant, statistical cut-off, fold-change, figure/table references, "
                    "or pathway enrichment statements."
                )
            elif "conclusion" in lower_column:
                extra_guidance = (
                    " If the paper has no explicit gene-specific conclusion sentence, summarize "
                    "the authors' supported interpretation from Results or Discussion for this gene."
                )
            prompt_text += f"- {column}: {description}. In the gene-only row (variant_name empty), provide gene-level facts that apply regardless of variant. In variant rows, include only variant-specific details; if none, leave empty.{extra_guidance}\n"
            prompt_text += f"- {column} Citation: Direct quote or section/page reference supporting {column}. Empty if the field is empty.\n"
        prompt_text += f"\nPaper text:\n{self.paper_text}"
        if self.table_inputs and getattr(config, "ENABLE_TABLE_CITATIONS", True):
            prompt_text += f"\n\n--- STRUCTURED TABLE DATA ---\n{self._format_table_summary_for_prompt()}"

        prompt_text += _DETAIL_EXTRACTION_CRITICAL_INSTRUCTIONS

        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])]

        max_retries = max(1, int(getattr(config, "GEMINI_MAX_RETRIES", 1)))

        for attempt in range(max_retries):
            try:
                full_response_text = self._generate_content_text(
                    model_name=model_name,
                    contents=contents,
                    generate_content_config=generate_content_config,
                    purpose="detail extraction",
                    optional=False,
                )

                parsed = json.loads(full_response_text)
                if isinstance(parsed, list):
                    for row in parsed:
                        if not isinstance(row, dict):
                            continue
                        row["variant_name"] = self._normalize_variant_value(
                            row.get("variant_name", "")
                        )
                        # Cleanup no-evidence placeholders so CSV stays clean.
                        for col in column_descriptions:
                            if col in row:
                                row[col] = self._normalize_empty_placeholder(row.get(col, ""))
                            citation_col = f"{col} Citation"
                            if citation_col in row:
                                row[citation_col] = self._normalize_empty_placeholder(
                                    row.get(citation_col, "")
                                )
                        # F11: Tag as LLM-sourced so the output CSV can
                        # distinguish real LLM content from fallback skeletons
                        # produced when Gemini fails (quota, timeout, malformed).
                        row["extraction_mode"] = "llm"
                    self.detail_extraction_status = (
                        "model_response_parsed" if parsed else "model_response_empty_rows"
                    )
                    self.detail_extraction_error = ""
                    self.detail_extraction_rows = len(parsed)
                return parsed

            except Exception as e:
                logging.error(
                    f"Error during gene info extraction (attempt {attempt + 1}/{max_retries}): {e}"
                )
                should_retry, wait = self._should_retry_gemini_error(e, attempt, max_retries)
                if should_retry:
                    logging.info(f"Retrying in {wait} seconds...")
                    time.sleep(wait)
                else:
                    logging.error("All retry attempts failed for gene info extraction")
                    self.detail_extraction_status = (
                        "quota_limited_fallback"
                        if self._is_rate_limit_error(e)
                        else "fallback_after_retries"
                    )
                    self.detail_extraction_error = str(e)
                    # Return minimal fallback with gene/variant only — no fabricated content.
                    # F11: every fallback row is tagged extraction_mode="skeleton" and carries
                    # the failure reason, so downstream code (confidence scoring, CSV output)
                    # can visibly downgrade these rows instead of presenting them like LLM rows.
                    err_msg = str(e)[:300]  # cap to keep CSV readable
                    fallback_data = []
                    for assoc in self.associations:
                        fallback_item = {
                            "gene_name": assoc["gene"],
                            "variant_name": self._normalize_variant_value(assoc.get("variant", "")),
                            "extraction_mode": "skeleton",
                            "detail_extraction_error": err_msg,
                        }
                        for col in column_descriptions:
                            fallback_item[col] = ""
                            fallback_item[f"{col} Citation"] = ""
                        fallback_data.append(fallback_item)
                    self.detail_extraction_rows = len(fallback_data)
                    return fallback_data

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
        context_validation = self._validate_and_prepare_paper_text()

        if context_validation["failed"]:
            logging.error("Context validation failed - cannot proceed with pipeline")
            return pd.DataFrame()

        # Steps 0.5–1.5: Candidate discovery
        self._run_candidate_discovery()

        # Step 1.6: Grounding check
        self._run_grounding_check()

        # Step 2: Gene validation + normalization
        self._run_validation_and_normalize()

        # Step 3: Detail extraction
        extracted_info = self._run_detail_extraction(column_descriptions)
        if not extracted_info:
            return pd.DataFrame()

        # Step 4: Post-validation (metadata, strict gate, citation, evidence gate)
        df = pd.DataFrame(extracted_info)
        if "variant_name" in df.columns:
            df["variant_name"] = df["variant_name"].apply(self._normalize_variant_value)
        return self._run_post_validation(df, column_descriptions, context_validation)

    # ------------------------------------------------------------------
    # run_pipeline sub-stages (extracted for readability, not reuse)
    # ------------------------------------------------------------------

    def _summarise_sources(self) -> Dict[str, int]:
        """Tracer helper: how many candidates carry each source tag."""
        counts: Dict[str, int] = {}
        for meta in self.candidate_meta.values():
            for src in (meta.get("sources") or []):
                counts[str(src)] = counts.get(str(src), 0) + 1
        return counts

    def _run_candidate_discovery(self) -> None:
        """Steps 0.5–1.5: Discover gene candidates from all sources."""
        # Reset candidate tracking for this run.
        self.candidate_meta = {}
        self.dropped_candidates = []
        self.strict_gate_drops = []
        self.evidence_gate_drops = []
        self.detail_extraction_status = "not_started"
        self.detail_extraction_error = ""
        self.detail_extraction_rows = 0
        self.associations = []

        # Step 0.5: Abstract gene discovery (independent pass, catches natural-language gene refs)
        # e.g. abstract says "IL-6" / "IFN-γ" while full text says "interleukin-6" / "interferon-gamma"
        if getattr(config, "ENABLE_ABSTRACT_GENE_DISCOVERY", True) and self.abstract_text:
            logging.info("Step 0.5: Extracting gene-variant associations from abstract")
            import time as _t
            t0 = _t.time()
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
                    duration_ms=(_t.time() - t0) * 1000.0,
                )

        import time as _t

        # Step 1: Optional LLM gene discovery on full paper text. Free-tier
        # defaults keep this off and rely on PubTator + deterministic seeding,
        # saving the quota for the detail-extraction call that creates output.
        if getattr(config, "ENABLE_LLM_GENE_DISCOVERY", False):
            logging.info("Step 1: Extracting gene-variant associations from paper text (pass 1)")
            t0 = _t.time()
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
                    duration_ms=(_t.time() - t0) * 1000.0,
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
                t0 = _t.time()
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
                        duration_ms=(_t.time() - t0) * 1000.0,
                    )
            except Exception as e:
                logging.warning(
                    f"Second gene discovery pass failed, continuing with pass-1 results: {e}"
                )
        else:
            logging.info("Step 1b: Skipping second Gemini gene discovery pass")

        # Step 1.1: Deterministic lexicon candidates (HGNC symbols/aliases)
        t0 = _t.time()
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
                duration_ms=(_t.time() - t0) * 1000.0,
            )

        # Step 1.25: Multimodal figure analysis (PMC figure images + captions)
        if getattr(config, "ENABLE_FIGURE_ANALYSIS", True) and self.figure_inputs:
            logging.info("Step 1.25: Extracting gene-variant associations from figures")
            t0 = _t.time()
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
                    duration_ms=(_t.time() - t0) * 1000.0,
                )

        # Step 1.5: HYBRID PIPELINE - Merge PubTator genes (ensures union)
        if self.pubtator_genes:
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
                                "sources": sorted(list(v.get("sources") or []))
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
            sources = meta.get("sources", set()) or set()
            if isinstance(sources, set) and sources == {"llm_figure"}:
                # Verify gene appears in at least one figure caption or label.
                # This is a lighter check than prose grounding — we're confirming
                # the gene was actually visible in the figures, not hallucinated.
                figure_text_lower = " ".join(
                    f"{fig.get('label', '')} {fig.get('caption', '')}"
                    for fig in (self.figure_inputs or [])
                ).lower()
                candidate_terms = [gene] + list(meta.get("raw_gene_labels") or [])
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
            for raw_label in meta.get("raw_gene_labels") or set():
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
                    f"Grounding check: dropping '{gene}' (raw: {list(meta.get('raw_gene_labels') or [])}) "
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
                 "sources": sorted(list(v.get("sources") or []))}
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
        import time as _t
        _t0 = _t.time()
        _assoc_count_in = len(self.associations)
        extracted_info = self.extract_gene_info(column_descriptions)

        # Merge duplicate rows: Stage 3 sometimes emits the same gene twice with different
        # fields filled (e.g. one row has Disease Association, another has Statistical Evidence).
        # Consolidate into one row per (gene_name, variant_name).
        if extracted_info and len(extracted_info) > 1:
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
                duration_ms=(_t.time() - _t0) * 1000.0,
            )
            pipeline_tracer.capture(
                "row_merge",
                pmid=self.pmid,
                outputs={"rows_after_merge": len(extracted_info or [])},
            )
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

            sources = set()
            meta = self.candidate_meta.get(key)
            if meta:
                src = meta.get("sources", set())
                if isinstance(src, set):
                    sources = {str(s) for s in src if s}
                elif isinstance(src, (list, tuple)):
                    sources = {str(s) for s in src if s}
                elif isinstance(src, str) and src:
                    sources = {src}
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
            pipeline_tracer.capture(
                "low_confidence_gate",
                pmid=self.pmid,
                outputs={
                    "dropped_count": len(low_conf),
                    "dropped": pipeline_tracer.summarise(low_conf),
                    "threshold": min_confidence,
                },
            )
            pipeline_tracer.capture(
                "corroboration_gate",
                pmid=self.pmid,
                outputs={
                    "dropped_count": len(corrob),
                    "dropped": pipeline_tracer.summarise(corrob),
                    "survivors": validated_count,
                },
            )

    def _add_candidate_provenance_metadata(self, df: pd.DataFrame):
        """
        Add candidate lifecycle provenance columns to aid trust/debugging.
        """
        if df.empty:
            return

        df["Candidate Source"] = ""
        df["Normalization Applied"] = ""
        df["Validation Outcome"] = ""
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

            sources = meta.get("sources", set())
            if isinstance(sources, set):
                df.at[i, "Candidate Source"] = ",".join(sorted(sources))
            else:
                df.at[i, "Candidate Source"] = str(sources)

            df.at[i, "Normalization Applied"] = meta.get("normalization_applied", "") or ""
            df.at[i, "Validation Outcome"] = meta.get("validation_outcome", "") or ""
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

        # Map results back to DataFrame rows (normalize case and variant placeholders)
        def _norm_gene(g: str) -> str:
            return (g or "").strip().upper()

        def _norm_variant(v: str) -> str:
            v = (v or "").strip()
            if v.upper() in {"N/A", "NA", "NONE"}:
                return ""
            return v

        for i, row in df.iterrows():
            gene_name = _norm_gene(row.get("gene_name", ""))
            variant_name = _norm_variant(row.get("variant_name", ""))

            # Look up gene biotype from local HGNC database
            if gene_name:
                df.at[i, "Gene Biotype"] = self.gene_validator.get_gene_biotype(gene_name)

            # Find matching validation result
            for result in self.validation_results:
                if (
                    _norm_gene(result.gene) == gene_name
                    and _norm_variant(result.variant) == variant_name
                ):
                    df.at[i, "validation_confidence"] = result.confidence_score
                    df.at[i, "validation_source"] = result.validation_source
                    df.at[i, "validation_suggestions"] = (
                        "; ".join(result.suggestions) if result.suggestions else ""
                    )
                    break

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

        from .gene_validator import _calculate_citation_confidence, _citation_exists_in_paper

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

        for i, row in df.iterrows():
            gene_symbol = str(row.get("gene_name", row.get("Gene/Group", "")))

            # Collect raw pre-normalization labels for this gene (e.g. "BNP" for NPPB).
            # Papers use aliases, not HGNC canonical symbols, so the gene context check
            # must accept any of: canonical symbol OR any raw label.
            variant_symbol = str(row.get("variant_name", "")).strip()
            meta_key = (gene_symbol.upper(), variant_symbol.upper())
            meta = self.candidate_meta.get(meta_key) or {}
            raw_labels = [str(r) for r in (meta.get("raw_gene_labels") or set()) if r]

            for content_col, citation_col in pairs:
                raw = row.get(citation_col, "")
                citation_text = str(raw).strip() if raw is not None and str(raw) != "nan" else ""

                # Skip empty fields and backfill placeholder — not real LLM citations
                if not citation_text or citation_text == "Auto snippet from paper text":
                    continue

                try:
                    exists, ratio, reason = _citation_exists_in_paper(
                        citation_text, self.paper_text, gene_symbol, gene_aliases=raw_labels,
                        tables=self.table_inputs
                    )
                    confidence = _calculate_citation_confidence(
                        citation_text, self.paper_text, exists, ratio
                    )
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

    # Section drop priority for context truncation (drop last = least important first).
    # Abstract and results are never dropped; introduction is dropped only as a last resort.
    _SECTION_DROP_ORDER = ["methods", "supplementary", "discussion", "conclusion", "introduction"]

    # Regex patterns for identifying named sections in paper text.
    # Each tuple: (section_key, compiled pattern matching the header line).
    _SECTION_HEADER_PATTERNS = [
        ("abstract", re.compile(r"^#{0,3}\s*Abstract\s*$", re.IGNORECASE | re.MULTILINE)),
        ("introduction", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?Introduction\s*$", re.IGNORECASE | re.MULTILINE)),
        ("methods", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?(?:Methods|Materials?\s*(?:and|&)\s*Methods?|Experimental\s*(?:Procedures?|Section|Methods?))\s*$", re.IGNORECASE | re.MULTILINE)),
        # Combined "Results and Discussion" must match BEFORE the standalone patterns so it maps
        # to "results" (never dropped) rather than letting the combined section go unrecognised.
        ("results", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?Results?\s*(?:and|&|/)\s*Discussion\s*$", re.IGNORECASE | re.MULTILINE)),
        ("results", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?Results?\s*$", re.IGNORECASE | re.MULTILINE)),
        ("discussion", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?Discussion\s*$", re.IGNORECASE | re.MULTILINE)),
        ("conclusion", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?Conclusions?\s*$", re.IGNORECASE | re.MULTILINE)),
        ("supplementary", re.compile(r"^#{0,3}\s*(?:\d+\.?\s*)?(?:Supplementary|Supporting)\s*(?:Information|Materials?|Data|Text|Methods?)?\s*$", re.IGNORECASE | re.MULTILINE)),
    ]

    @staticmethod
    def _split_paper_into_named_sections(text: str) -> Dict[str, str]:
        """Split paper text into named sections based on header patterns.

        Returns a dict mapping section keys to their text content.
        Text before the first recognised header is stored under '_preamble'.
        The final section extends to end-of-text (includes references etc.).
        """
        # Find all header matches with positions
        matches: List[Tuple[int, str]] = []
        for key, pattern in GeneInfoPipeline._SECTION_HEADER_PATTERNS:
            for m in pattern.finditer(text):
                matches.append((m.start(), key))

        if not matches:
            # No recognisable sections — return all text as preamble
            return {"_preamble": text}

        matches.sort(key=lambda x: x[0])

        sections: Dict[str, str] = {}
        # Text before first header
        if matches[0][0] > 0:
            sections["_preamble"] = text[: matches[0][0]]

        for i, (start, key) in enumerate(matches):
            end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
            if key in sections:
                sections[key] += "\n\n" + text[start:end]
            else:
                sections[key] = text[start:end]

        return sections

    def _validate_and_prepare_paper_text(self) -> Dict[str, Any]:
        """
        Validate paper text against model context windows and prepare for processing.

        If estimated tokens exceed 80% of the flash context limit, sections are
        iteratively removed in priority order (methods -> supplementary -> discussion
        -> conclusion -> introduction) until the estimate drops below 80%.  Abstract
        and results are always preserved.

        If after truncation (or originally) tokens exceed 95% of the limit, a
        user-visible warning is recorded and ``context_truncated`` is set to True.

        Returns:
            Dictionary with validation results and any modifications made
        """
        from . import config

        if not config.ENABLE_CONTEXT_CHECKING:
            return {
                "failed": False,
                "flash_fits": True,
                "pro_fits": True,
                "original_tokens": 0,
                "modifications": "Context checking disabled",
                "truncation_applied": False,
                "context_truncated": False,
            }

        # Estimate token count for the original text
        try:
            original_tokens = ContextWindowValidator.estimate_token_count(
                self.original_paper_text
            )
        except Exception as e:
            logging.warning(f"Context validation unavailable ({e}); skipping context checks")
            return {
                "failed": False,
                "flash_fits": True,
                "pro_fits": True,
                "original_tokens": 0,
                "modifications": "Context check unavailable",
                "truncation_applied": False,
                "context_truncated": False,
            }

        flash_limit = config.GEMINI_FLASH_CONTEXT_LIMIT
        threshold_80 = int(flash_limit * 0.80)
        threshold_95 = int(flash_limit * 0.95)

        logging.info(
            f"Context validation — estimated {original_tokens:,} tokens "
            f"(80% limit={threshold_80:,}, 95% limit={threshold_95:,})"
        )

        truncation_applied = False
        removed_sections: List[str] = []
        current_tokens = original_tokens

        # --- Section-aware truncation if >80% of context limit ---
        if current_tokens > threshold_80:
            logging.warning(
                f"Paper text ({current_tokens:,} tokens) exceeds 80% of flash context "
                f"({threshold_80:,}) — applying section-aware truncation"
            )

            sections = self._split_paper_into_named_sections(self.original_paper_text)

            for section_key in self._SECTION_DROP_ORDER:
                if current_tokens <= threshold_80:
                    break
                if section_key not in sections:
                    continue

                dropped_tokens = ContextWindowValidator.estimate_token_count(
                    sections[section_key]
                )
                del sections[section_key]
                removed_sections.append(section_key)
                current_tokens -= dropped_tokens
                logging.info(
                    f"  Dropped '{section_key}' (~{dropped_tokens:,} tokens) — "
                    f"now ~{current_tokens:,} tokens"
                )

            # Reassemble paper text from remaining sections (preserving original order)
            ordered_keys = []
            if "_preamble" in sections:
                ordered_keys.append("_preamble")
            for key, _ in self._SECTION_HEADER_PATTERNS:
                if key in sections and key not in ordered_keys:
                    ordered_keys.append(key)
            if "_remainder" in sections:
                ordered_keys.append("_remainder")
            # Include any keys we didn't explicitly order (defensive)
            for key in sections:
                if key not in ordered_keys:
                    ordered_keys.append(key)

            self.paper_text = "\n\n".join(sections[k] for k in ordered_keys)
            truncation_applied = True

        # --- Check if still >95% — emit user-visible warning ---
        context_truncated = current_tokens > threshold_95
        if context_truncated:
            warn_msg = (
                f"Paper content is very large ({current_tokens:,} tokens, "
                f">{threshold_95:,} limit). Gemini may silently drop text — "
                f"results for this paper should be reviewed carefully."
            )
            logging.warning(warn_msg)
            # Store warning for orchestrator to surface via log_callback
            self._context_warning = warn_msg

        # Build modifications description
        if removed_sections:
            modifications = (
                f"Truncated {'+'.join(removed_sections)}: "
                f"{original_tokens:,}→{current_tokens:,} tokens"
            )
        elif context_truncated:
            modifications = (
                f"No sections removed but content still large: "
                f"{original_tokens:,} tokens (>{threshold_95:,})"
            )
        else:
            modifications = "No modifications needed"

        flash_fits = current_tokens <= threshold_80
        pro_fits = current_tokens <= int(config.GEMINI_PRO_CONTEXT_LIMIT * 0.80)

        return {
            "failed": False,
            "flash_fits": flash_fits,
            "pro_fits": pro_fits,
            "original_tokens": original_tokens,
            "modifications": modifications,
            "truncation_applied": truncation_applied,
            "context_truncated": context_truncated,
        }

    def _add_context_metadata(self, df: pd.DataFrame, context_validation: Dict[str, any]):
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
