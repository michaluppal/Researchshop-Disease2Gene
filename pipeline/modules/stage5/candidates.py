"""Candidate normalization, provenance, and deterministic HGNC scanning."""

import re
from typing import Any, Dict, List, Set, Tuple

from .. import config


class CandidateMixin:
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
