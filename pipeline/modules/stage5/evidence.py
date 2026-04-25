"""Evidence search, backfill, deterministic-context rescue, and evidence gates."""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from .. import config


class EvidenceMixin:
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
