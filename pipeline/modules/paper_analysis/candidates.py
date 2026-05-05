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

    @classmethod
    def _normalize_variant_for_gene(cls, gene: str, value: Any) -> str:
        """Normalize gene-scoped variant shorthand without changing generic variants."""
        variant = cls._normalize_variant_value(value)
        gene_u = str(gene or "").strip().upper()
        if not variant or not gene_u.startswith("HLA-"):
            return variant

        match = re.match(
            r"^(?:HLA[-\s]*)?([A-Z])w?\*?(\d{2,4}(?::\d{2,4}){0,3})$",
            variant.strip(),
            flags=re.IGNORECASE,
        )
        if not match:
            return variant
        allele_locus = match.group(1).upper()
        gene_locus = gene_u.split("-", 1)[1][:1]
        if allele_locus != gene_locus:
            return variant
        return f"HLA-{allele_locus}*{match.group(2)}"

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

    @staticmethod
    def _as_string_set(value: Any) -> Set[str]:
        """Normalize metadata values that may be a string, list, tuple, or set."""
        if isinstance(value, str):
            text = value.strip()
            return {text} if text else set()
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if item and str(item).strip()}
        return set()

    def _as_sorted_strings(self, value: Any) -> List[str]:
        return sorted(self._as_string_set(value))

    @staticmethod
    def _as_string_list(value: Any) -> List[str]:
        """Normalize metadata values to a de-duplicated list while preserving order."""
        if value is None:
            return []
        if isinstance(value, str):
            iterable = [value]
        elif isinstance(value, (list, tuple, set)):
            iterable = list(value)
        else:
            iterable = [value]

        out: List[str] = []
        seen: Set[str] = set()
        for item in iterable:
            text = str(item or "").strip()
            if not text:
                continue
            marker = text.upper()
            if marker in seen:
                continue
            seen.add(marker)
            out.append(text)
        return out

    def _merge_string_lists(self, existing: Any, additions: Any) -> List[str]:
        return self._as_string_list(self._as_string_list(existing) + self._as_string_list(additions))

    @staticmethod
    def _normalization_record_to_dict(record: Any) -> Dict[str, str]:
        return {
            "original_mention": str(getattr(record, "original_mention", "") or ""),
            "normalized_gene": str(getattr(record, "normalized_gene", "") or ""),
            "normalized_variant": str(getattr(record, "normalized_variant", "") or ""),
            "evidence_sentence": str(getattr(record, "evidence_sentence", "") or ""),
            "normalization_rule": str(getattr(record, "normalization_rule", "") or ""),
        }

    def _normalization_records_for_candidate(
        self,
        gene: str,
        variant: str = "",
    ) -> List[Dict[str, str]]:
        prepared = getattr(self, "prepared_content", None)
        if prepared is None or not hasattr(prepared, "records_for_gene"):
            return []

        gene_u = (gene or "").strip().upper()
        variant_u = self._normalize_variant_for_gene(gene_u, variant).upper()
        records: List[Dict[str, str]] = []
        for record in prepared.records_for_gene(gene_u):
            payload = self._normalization_record_to_dict(record)
            record_variant = self._normalize_variant_for_gene(
                payload["normalized_gene"],
                payload["normalized_variant"],
            ).upper()
            if variant_u and record_variant and record_variant != variant_u:
                continue
            if not variant_u and record_variant:
                continue
            records.append(payload)
        return records

    def _refresh_candidate_cache(self, key: Tuple[str, str]) -> None:
        """Materialize candidate-derived values once for later per-paper extraction gates."""
        if not hasattr(self, "_candidate_terms_cache"):
            self._candidate_terms_cache = {}
        meta = self.candidate_meta.get(key)
        if not meta:
            return

        sources = self._as_string_set(meta.get("sources"))
        raw_labels = self._as_string_set(meta.get("raw_gene_labels"))
        gene = str(meta.get("gene") or key[0]).strip()
        variant = self._normalize_variant_for_gene(gene, meta.get("variant", key[1]))
        reported_gene = str(meta.get("reported_gene") or "").strip()
        original_mentions = self._as_string_list(meta.get("original_mentions"))
        normalization_records = self._normalization_records_for_candidate(gene, variant)
        normalization_mentions = [
            record["original_mention"]
            for record in normalization_records
            if record.get("original_mention")
        ]
        if reported_gene:
            raw_labels.add(reported_gene)
        raw_labels.update(original_mentions)
        raw_labels.update(normalization_mentions)

        meta["sources"] = sources
        meta["raw_gene_labels"] = raw_labels
        meta["original_mentions"] = self._merge_string_lists(
            original_mentions,
            normalization_mentions,
        )
        meta["normalization_records"] = normalization_records
        meta["sources_list"] = sorted(sources)
        meta["raw_gene_labels_list"] = sorted(raw_labels)

        terms: List[str] = []
        if variant:
            terms.append(variant)
        if gene:
            terms.append(gene)
        terms.extend(sorted(raw_labels))
        terms.extend(self._get_hgnc_aliases_for_gene(gene))
        terms.extend(normalization_mentions)

        deduped: List[str] = []
        seen: Set[str] = set()
        for term in terms:
            marker = str(term or "").strip().upper()
            if not marker or marker in seen:
                continue
            seen.add(marker)
            deduped.append(str(term).strip())

        meta["candidate_terms"] = deduped
        meta["association_type"] = self._infer_candidate_association_type(meta)
        self._candidate_terms_cache[(gene.upper(), variant.upper())] = list(deduped)

    def _refresh_all_candidate_caches(self) -> None:
        for key in list(self.candidate_meta.keys()):
            self._refresh_candidate_cache(key)

    def _infer_candidate_association_type(self, meta: Dict[str, Any]) -> str:
        """Coarse row intent used to separate genetics from pathway mentions."""
        sources = self._as_string_set(meta.get("sources"))
        variant = self._normalize_variant_for_gene(
            str(meta.get("gene") or ""),
            meta.get("variant", ""),
        )
        context_reason = str(meta.get("deterministic_context_reason") or "")

        if variant:
            return "variant_association"
        if "llm_figure" in sources:
            return "figure_derived_gene"
        if context_reason == "pathway_context":
            return "mechanistic_pathway_gene"
        if context_reason == "result_context":
            return "mechanistic_or_biomarker_gene"
        if "pubtator" in sources:
            return "pubtator_supported_gene"
        if sources == {"deterministic_lexicon"}:
            return "deterministic_candidate"
        if sources & {"llm_text", "llm_abstract"}:
            return "llm_supported_gene"
        return "candidate_gene"

    def _get_hgnc_aliases_for_gene(self, gene: str) -> List[str]:
        """
        Return HGNC alias_symbol + prev_symbol entries for the given canonical gene symbol.
        Used by alias-aware evidence backfill to find genes referenced by natural language names.
        """
        gene_u = (gene or "").strip().upper()
        if not hasattr(self, "_hgnc_alias_cache"):
            self._hgnc_alias_cache = {}
        if gene_u in self._hgnc_alias_cache:
            return list(self._hgnc_alias_cache[gene_u])

        db = getattr(self.gene_validator, "_local_gene_db", None) or {}
        if not db:
            return []

        info = db.get(gene_u) or {}
        aliases = list(info.get("alias_symbol") or info.get("aliases") or [])
        prevs = list(info.get("prev_symbol") or info.get("prev_symbols") or [])
        all_terms = [str(a).strip() for a in aliases + prevs if str(a).strip()]
        # Cap at 15 to avoid exploding search with genes that have many aliases
        cached = all_terms[:15]
        self._hgnc_alias_cache[gene_u] = cached
        return list(cached)

    def _candidate_terms_for_row(self, gene: str, variant: str) -> List[str]:
        """
        Build search terms for deterministic evidence backfill.
        """
        key = self._assoc_key(gene, variant)
        meta = self.candidate_meta.get(key)
        if meta and meta.get("candidate_terms"):
            return list(meta["candidate_terms"])
        if key in getattr(self, "_candidate_terms_cache", {}):
            return list(self._candidate_terms_cache[key])

        terms: List[str] = []
        if variant:
            terms.append(variant)
        if gene:
            terms.append(gene)

        meta = meta or {}
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
        self._candidate_terms_cache[key] = list(deduped)
        if meta:
            meta["candidate_terms"] = list(deduped)
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
                gene_raw = (assoc.get("reported_gene") or assoc.get("gene") or "").strip()
                variant_raw = assoc.get("reported_variant")
                if variant_raw is None:
                    variant_raw = assoc.get("variant", "")
                reported_variant = str(variant_raw or "").strip()
                original_mentions = self._as_string_list(assoc.get("original_mentions"))
                original_mention = str(assoc.get("original_mention") or "").strip()
                if original_mention:
                    original_mentions = self._merge_string_lists(
                        original_mentions,
                        [original_mention],
                    )
                evidence_sentence = str(assoc.get("evidence_sentence") or "").strip()
            else:
                if not assoc:
                    continue
                gene_raw = str(assoc[0] if len(assoc) > 0 else "").strip()
                variant_raw = assoc[1] if len(assoc) > 1 else ""
                reported_variant = str(variant_raw or "").strip()
                original_mentions = []
                evidence_sentence = ""

            if not gene_raw:
                continue

            gene_norm, norm_note = self._normalize_gene_symbol(gene_raw)
            if not gene_norm:
                continue
            variant_norm = self._normalize_variant_for_gene(gene_norm, variant_raw)

            key = self._assoc_key(gene_norm, variant_norm)
            entry = self.candidate_meta.get(key)
            if entry is None:
                entry = {
                    "gene": gene_norm,
                    "variant": variant_norm,
                    "sources": set(),
                    "normalization_applied": norm_note,
                    "raw_gene_labels": set([gene_raw, *original_mentions]),
                    "reported_gene": gene_raw,
                    "reported_variant": reported_variant,
                    "original_mentions": list(original_mentions),
                    "evidence_sentence": evidence_sentence,
                }
                self.candidate_meta[key] = entry
                added += 1
            else:
                raw_labels = self._as_string_set(entry.get("raw_gene_labels"))
                raw_labels.add(gene_raw)
                raw_labels.update(original_mentions)
                entry["raw_gene_labels"] = raw_labels
                entry.setdefault("reported_gene", gene_raw)
                if reported_variant and not entry.get("reported_variant"):
                    entry["reported_variant"] = reported_variant
                entry["original_mentions"] = self._merge_string_lists(
                    entry.get("original_mentions"),
                    original_mentions,
                )
                if evidence_sentence and not entry.get("evidence_sentence"):
                    entry["evidence_sentence"] = evidence_sentence
                if norm_note and not entry.get("normalization_applied"):
                    entry["normalization_applied"] = norm_note

            entry["sources"] = self._as_string_set(entry.get("sources"))
            entry["sources"].add(source)
            self._refresh_candidate_cache(key)

        self._refresh_associations_from_meta()
        return added

    def _refresh_associations_from_meta(self):
        self._refresh_all_candidate_caches()
        self.associations = []
        for entry in self.candidate_meta.values():
            gene = str(entry.get("gene", "") or "")
            self.associations.append(
                {
                    "gene": gene,
                    "variant": self._normalize_variant_for_gene(
                        gene,
                        entry.get("variant", ""),
                    ),
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
