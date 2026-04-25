"""Paper context-window validation and section-aware truncation."""

import logging
import re
from typing import Any, Dict, List, Tuple

from .. import config
from ..gene_validator import ContextWindowValidator


class ContextMixin:
    _SECTION_DROP_ORDER = ["methods", "supplementary", "discussion", "conclusion", "introduction"]
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
        for key, pattern in ContextMixin._SECTION_HEADER_PATTERNS:
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
