"""
Gene and Variant Validation Module

This module provides heuristics for validating gene and variant names extracted by AI models
against known databases of human genes and mutations using real APIs.
"""

import json
import logging
import re
import os
import math
import requests
import time
from typing import Dict, List, Tuple, Set, Optional
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class CitationValidationResult:
    """Result of citation validation."""

    field_name: str
    provided_citation: str
    citation_exists: bool
    confidence_score: float
    validation_details: str


@dataclass
class GeneValidationResult:
    """Result of gene/variant validation."""

    gene: str
    variant: str
    is_valid_gene: bool
    is_valid_variant: bool
    confidence_score: float
    validation_source: str
    suggestions: List[str] = None


class GeneValidator:
    """
    Validates gene names and variants against real databases using APIs.

    Uses multiple validation sources:
    1. HGNC (HUGO Gene Nomenclature Committee) API for gene symbols
    2. MyGene.info API for comprehensive gene information
    3. HGVS variant nomenclature patterns
    4. Rate limiting and caching for performance
    """

    def __init__(self):
        self.variant_patterns = self._compile_variant_patterns()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ResearchShop/1.0"})
        # Cache for gene lookups to avoid repeated API calls
        self._gene_cache = {}
        # Load local HGNC database for fast lookups
        self._local_gene_db = self._load_local_hgnc_database()

    def _load_local_hgnc_database(self) -> Dict[str, Dict]:
        """Load local HGNC gene database for fast validation."""
        import json
        from pathlib import Path

        hgnc_path = (
            Path(__file__).parent.parent / "data" / "reference" / "hgnc_genes.json"
        )

        if hgnc_path.exists():
            try:
                with open(hgnc_path, "r") as f:
                    gene_db = json.load(f)
                logger.info(f"Loaded {len(gene_db)} genes from local HGNC database")
                return gene_db
            except Exception as e:
                logger.warning(f"Failed to load local HGNC database: {e}")
        else:
            logger.warning(f"Local HGNC database not found at {hgnc_path}")

        return {}

    @lru_cache(maxsize=2000)
    def _validate_gene_hgnc(self, gene_symbol: str) -> Optional[Dict]:
        """
        Validate gene using local HGNC database first, then REST API as fallback.
        https://www.genenames.org/help/rest/
        """
        # Check local database first (fast)
        if self._local_gene_db and gene_symbol.upper() in self._local_gene_db:
            gene_info = self._local_gene_db[gene_symbol.upper()]
            return {
                "symbol": gene_info.get("symbol"),
                "name": gene_info.get("name"),
                "source": "HGNC_local",
            }

        # Fallback to API if local database unavailable or gene not found
        try:
            url = f"https://rest.genenames.org/fetch/symbol/{gene_symbol}"
            headers = {"Accept": "application/json"}
            response = self.session.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("response", {}).get("numFound", 0) > 0:
                    docs = data["response"]["docs"]
                    if docs:
                        return {
                            "symbol": docs[0].get("symbol"),
                            "name": docs[0].get("name"),
                            "hgnc_id": docs[0].get("hgnc_id"),
                            "source": "HGNC_API",
                        }
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.debug(f"HGNC API lookup failed for {gene_symbol}: {e}")
        return None

    @lru_cache(maxsize=2000)
    def _validate_gene_mygene(self, gene_symbol: str) -> Optional[Dict]:
        """
        Validate gene using MyGene.info API.
        https://mygene.info/
        """
        try:
            url = "https://mygene.info/v3/query"
            params = {
                "q": f"symbol:{gene_symbol} AND taxid:9606",  # Human genes only
                "fields": "symbol,name,entrezgene,ensembl.gene",
                "species": "human",
                "size": 1,
            }
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("total", 0) > 0 and data.get("hits"):
                    hit = data["hits"][0]
                    return {
                        "symbol": hit.get("symbol"),
                        "name": hit.get("name"),
                        "entrez_id": hit.get("entrezgene"),
                        "source": "MyGene.info",
                    }
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.debug(f"MyGene.info lookup failed for {gene_symbol}: {e}")
        return None

    def _compile_variant_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for common variant formats."""
        return {
            "hgvs_protein": re.compile(r"^p\.[A-Z][a-z]{2}\d+[A-Z*]?$"),
            "hgvs_coding": re.compile(r"^c\.\d+[A-Z]>[A-Z]$"),
            "hgvs_genomic": re.compile(r"^g\.\d+[A-Z]>[A-Z]$"),
            "dbsnp_rsid": re.compile(r"^rs\d+$", re.IGNORECASE),
            "amino_acid_substitution": re.compile(r"^[A-Z]\d+[A-Z]$"),
            "exon_deletion": re.compile(r"^exon\s+\d+\s+deletion$", re.IGNORECASE),
            "frameshift": re.compile(r"^fs\d+$"),
            "nonsense": re.compile(r"^X\d+$"),
            "splice_site": re.compile(r"^IVS\d+[+-]\d+$"),
        }

    def _is_valid_gene(self, gene_name: str) -> Tuple[bool, str, List[str]]:
        """
        Check if a gene name exists using real APIs.
        Returns (is_valid, source, suggestions)
        """
        if not gene_name or len(gene_name) < 2:
            return False, "invalid_format", []

        gene_upper = gene_name.upper().strip()
        # Resolve aliases using local HGNC database if available
        if self._local_gene_db:
            # Direct match
            if gene_upper in self._local_gene_db:
                pass
            else:
                # Search alias_symbol and prev_symbol maps
                try:
                    # Build inverted alias index on first use and cache it
                    if not hasattr(self, "_alias_index"):
                        alias_index = {}
                        for sym_u, info in self._local_gene_db.items():
                            for a in info.get("alias_symbol", []) or []:
                                alias_index.setdefault(a.upper(), sym_u)
                            for p in info.get("prev_symbol", []) or []:
                                alias_index.setdefault(p.upper(), sym_u)
                        self._alias_index = alias_index
                    target = self._alias_index.get(gene_upper)
                    if target:
                        gene_upper = target
                except Exception:
                    pass

        # Check cache first
        if gene_upper in self._gene_cache:
            cached = self._gene_cache[gene_upper]
            return cached["valid"], cached["source"], cached.get("suggestions", [])

        # Try HGNC first (authoritative source)
        hgnc_result = self._validate_gene_hgnc(gene_upper)
        if hgnc_result:
            # Use the actual source from the result (HGNC_local or HGNC_API)
            source_name = hgnc_result.get("source", "HGNC")
            self._gene_cache[gene_upper] = {
                "valid": True,
                "source": source_name,
                "data": hgnc_result,
            }
            return True, source_name, []

        # Fallback to MyGene.info
        mygene_result = self._validate_gene_mygene(gene_upper)
        if mygene_result:
            self._gene_cache[gene_upper] = {
                "valid": True,
                "source": "MyGene.info",
                "data": mygene_result,
            }
            return True, "MyGene.info", []

        # Try fuzzy matching for common misspellings
        suggestions = self._fuzzy_match_gene(gene_upper)
        self._gene_cache[gene_upper] = {
            "valid": False,
            "source": "not_found",
            "suggestions": suggestions,
        }

        if suggestions:
            return False, "fuzzy_match", suggestions

        return False, "not_found", []

    def _is_valid_variant(self, variant: str) -> Tuple[bool, str]:
        """
        Check if variant follows standard HGVS nomenclature.
        Returns (is_valid, matched_pattern)
        """
        if not variant:
            return False, "empty"

        # Check against HGVS patterns
        for pattern_name, pattern in self.variant_patterns.items():
            if pattern.match(variant.strip()):
                return True, pattern_name

        return False, "no_match"

    def _fuzzy_match_gene(self, gene_name: str) -> List[str]:
        """
        Find similar gene names using API search.
        """
        try:
            # Use MyGene.info fuzzy search
            url = "https://mygene.info/v3/query"
            params = {"q": gene_name, "fields": "symbol", "species": "human", "size": 3}
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get("hits"):
                    return [
                        hit.get("symbol", "")
                        for hit in data["hits"]
                        if hit.get("symbol")
                    ]
        except Exception as e:
            logger.debug(f"Fuzzy match failed for {gene_name}: {e}")

        return []

    def validate_gene_variant(
        self, gene: str, variant: str = ""
    ) -> GeneValidationResult:
        """
        Validate a gene-variant pair against known databases.

        Args:
            gene: Gene symbol (e.g., "BRCA1")
            variant: Variant notation (e.g., "p.Arg175His", optional)

        Returns:
            GeneValidationResult with validation details
        """
        is_valid_gene, gene_source, gene_suggestions = self._is_valid_gene(gene)
        is_valid_variant = False
        variant_source = "none"

        if variant:
            is_valid_variant, variant_source = self._is_valid_variant(variant)

        # Calculate confidence score
        confidence = 0.0
        if is_valid_gene:
            confidence += 0.7
        if variant and is_valid_variant:
            confidence += 0.3
        elif not variant:
            # If no variant provided, gene validation is sufficient
            # Confidence = 1.0 means: valid gene, no variant specified (gene-level association)
            confidence = 1.0 if is_valid_gene else 0.0

        validation_source = f"{gene_source}"
        if variant:
            validation_source += f" + variant_{variant_source}"

        return GeneValidationResult(
            gene=gene,
            variant=variant,
            is_valid_gene=is_valid_gene,
            is_valid_variant=(
                is_valid_variant if variant else True
            ),  # True if no variant specified
            confidence_score=confidence,
            validation_source=validation_source,
            suggestions=gene_suggestions,
        )

    def validate_associations(self, associations: List) -> List[GeneValidationResult]:
        """
        Validate a list of gene-variant associations.

        Args:
            associations: List of (gene, variant) tuples OR list of dicts with 'gene' and 'variant' keys

        Returns:
            List of GeneValidationResult objects
        """
        results = []
        for assoc in associations:
            # Handle both tuple and dict formats
            if isinstance(assoc, dict):
                gene = assoc.get("gene", "")
                variant = assoc.get("variant", "")
                # Normalize placeholders
                if isinstance(variant, str) and variant.upper() in {
                    "N/A",
                    "NA",
                    "NONE",
                }:
                    variant = ""
            else:
                gene, variant = assoc

            result = self.validate_gene_variant(gene, variant)
            results.append(result)
            logger.info(
                f"Validated gene variant: gene_valid={result.is_valid_gene}, "
                f"variant_valid={result.is_valid_variant}, confidence={result.confidence_score:.2f}"
            )

        return results

    def filter_valid_associations(
        self, associations: List, min_confidence: float = 0.7
    ) -> List:
        """
        Filter associations to only include those that pass validation.

        Args:
            associations: List of (gene, variant) tuples OR list of dicts with 'gene' and 'variant' keys
            min_confidence: Minimum confidence score to keep (0-1)

        Returns:
            Filtered list of validated associations (same format as input)
        """
        results = self.validate_associations(associations)
        valid_associations = []

        for assoc, result in zip(associations, results):
            if result.confidence_score >= min_confidence:
                valid_associations.append(assoc)  # Keep original format
            else:
                logger.warning(
                    f"Filtered out gene variant (confidence: {result.confidence_score:.2f} < {min_confidence})"
                )

        return valid_associations


# Citation validation functions
def validate_citations(
    ai_response: Dict[str, str], paper_text: str
) -> List[CitationValidationResult]:
    """
    Validate that citations provided by AI actually exist in the paper.

    Args:
        ai_response: Dictionary mapping field names to their values with citations
        paper_text: Full text of the paper

    Returns:
        List of CitationValidationResult objects
    """
    results = []

    for field_name, response_text in ai_response.items():
        # Extract citation from response (assumes format like: "Answer. Citation: 'quoted text'")
        citation = _extract_citation_from_response(response_text)

        if citation:
            exists = _citation_exists_in_paper(citation, paper_text)
            confidence = _calculate_citation_confidence(citation, paper_text, exists)

            results.append(
                CitationValidationResult(
                    field_name=field_name,
                    provided_citation=citation,
                    citation_exists=exists,
                    confidence_score=confidence,
                    validation_details=f"Citation {'found' if exists else 'NOT FOUND'} in paper",
                )
            )

            if not exists:
                logger.warning(
                    f"Citation validation FAILED for {field_name}: '{citation}' not found in paper"
                )
        else:
            results.append(
                CitationValidationResult(
                    field_name=field_name,
                    provided_citation="",
                    citation_exists=False,
                    confidence_score=0.0,
                    validation_details="No citation provided in response",
                )
            )

    return results


def _extract_citation_from_response(response_text: str) -> str:
    """Extract citation text from AI response."""
    if not response_text:
        return ""

    # Try to find citation patterns
    patterns = [
        r'Citation:\s*["\']([^"\']+)["\']',  # Citation: "text"
        r"Citation:\s*(.+?)(?:\n|$)",  # Citation: text
        r"\[Citation:\s*([^\]]+)\]",  # [Citation: text]
        r'"([^"]{20,})"',  # Any quoted text > 20 chars
    ]

    for pattern in patterns:
        match = re.search(pattern, response_text, re.IGNORECASE)
        if match:
            citation = match.group(1).strip()
            if len(citation) > 10:  # Minimum length for meaningful citation
                return citation

    return ""


def _citation_exists_in_paper(citation: str, paper_text: str) -> bool:
    """Check if citation text exists in the paper."""
    if not citation or not paper_text:
        return False

    # Normalize both texts for comparison
    citation_normalized = " ".join(citation.lower().split())
    paper_normalized = " ".join(paper_text.lower().split())

    # Exact match
    if citation_normalized in paper_normalized:
        return True

    # Fuzzy match - check if significant portions exist
    words = citation_normalized.split()
    if len(words) >= 5:
        # Check if at least 80% of words appear in order
        words_found = 0
        for word in words:
            if len(word) > 3 and word in paper_normalized:  # Skip short words
                words_found += 1

        if words_found / len(words) >= 0.8:
            return True

    return False


def _calculate_citation_confidence(
    citation: str, paper_text: str, exists: bool
) -> float:
    """Calculate confidence score for citation validation."""
    if not exists:
        return 0.0

    # Base confidence if citation exists
    confidence = 0.7

    # Boost confidence based on citation length (longer = more specific)
    citation_length = len(citation.split())
    if citation_length >= 20:
        confidence += 0.2
    elif citation_length >= 10:
        confidence += 0.1

    # Boost if exact match (not just fuzzy)
    citation_normalized = " ".join(citation.lower().split())
    paper_normalized = " ".join(paper_text.lower().split())
    if citation_normalized in paper_normalized:
        confidence += 0.1

    return min(confidence, 1.0)


# Context window validation
class ContextWindowValidator:
    """Validates that paper content fits within model context windows."""

    # Token limits for Gemini models (approximate, with safety margin)
    GEMINI_FLASH_LIMIT = 1000000  # 1M tokens
    GEMINI_PRO_LIMIT = 2000000  # 2M tokens
    SAFETY_MARGIN = 0.9  # Use 90% of limit to be safe

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        Estimate token count for text.
        Rough approximation: ~0.75 tokens per word for English.
        """
        if not text:
            return 0

        # Simple word-based estimation
        words = len(text.split())
        estimated_tokens = int(words * 0.75)

        return estimated_tokens

    @staticmethod
    def check_context_fit(
        text: str, model_name: str = "flash"
    ) -> Tuple[bool, int, int]:
        """
        Check if text fits within model's context window.

        Args:
            text: Text to check
            model_name: "flash" or "pro"

        Returns:
            (fits, estimated_tokens, limit)
        """
        estimated_tokens = ContextWindowValidator.estimate_token_count(text)

        if model_name.lower() == "flash":
            limit = int(
                ContextWindowValidator.GEMINI_FLASH_LIMIT
                * ContextWindowValidator.SAFETY_MARGIN
            )
        else:
            limit = int(
                ContextWindowValidator.GEMINI_PRO_LIMIT
                * ContextWindowValidator.SAFETY_MARGIN
            )

        fits = estimated_tokens <= limit

        return fits, estimated_tokens, limit

    @staticmethod
    def validate_paper_context(paper_text: str) -> Dict[str, dict]:
        """
        Validate paper text against both model context windows.

        Args:
            paper_text: Full paper text to validate

        Returns:
            Dictionary with validation results for both flash and pro models
        """
        from . import config

        # Get actual model names from config
        flash_model_name = config.GEMINI_CONFIG.get(
            "gene_extraction_model", "gemini-2.0-flash"
        )
        pro_model_name = config.GEMINI_CONFIG.get(
            "data_extraction_model", "gemini-2.5-flash"
        )

        results = {}

        # Check flash model
        flash_fits, flash_tokens, flash_limit = (
            ContextWindowValidator.check_context_fit(paper_text, "flash")
        )
        results["flash_model"] = {
            "fits": flash_fits,
            "estimated_tokens": flash_tokens,
            "recommendation": (
                f"Text fits within {flash_model_name} context limit ({flash_tokens:,} < {flash_limit:,} tokens)"
                if flash_fits
                else f"Text exceeds {flash_model_name} context limit ({flash_tokens:,} > {flash_limit:,} tokens). Paper will be skipped."
            ),
        }

        # Check pro model (using data extraction model name)
        pro_fits, pro_tokens, pro_limit = ContextWindowValidator.check_context_fit(
            paper_text, "pro"
        )
        results["pro_model"] = {
            "fits": pro_fits,
            "estimated_tokens": pro_tokens,
            "recommendation": (
                f"Text fits within {pro_model_name} context limit ({pro_tokens:,} < {pro_limit:,} tokens)"
                if pro_fits
                else f"Text exceeds {pro_model_name} context limit ({pro_tokens:,} > {pro_limit:,} tokens). Paper will be skipped."
            ),
        }

        return results


def validate_paper_context_fit(
    paper_text: str, model_name: str = "flash"
) -> Dict[str, object]:
    """
    Validates paper fits within model context window.

    Args:
        paper_text: Paper text to validate
        model_name: "flash" or "pro"

    Returns:
        Dictionary with validation results
    """
    fits, tokens, limit = ContextWindowValidator.check_context_fit(
        paper_text, model_name
    )

    result = {
        "fits": fits,
        "estimated_tokens": tokens,
        "token_limit": limit,
        "utilization": tokens / limit if limit > 0 else 0,
        "skip_paper": not fits,  # Paper will be skipped if it exceeds context
    }

    if not fits:
        logger.warning(
            f"Paper text ({tokens} tokens) exceeds {model_name} context limit ({limit} tokens) - will be skipped"
        )
    else:
        logger.info(
            f"Paper text fits within {model_name} context: {tokens}/{limit} tokens ({result['utilization']:.1%})"
        )

    return result


def validate_extracted_genes(genes_df, validator: Optional[GeneValidator] = None):
    """
    Validate extracted genes from dataframe.

    Args:
        genes_df: DataFrame with 'gene' and 'variant' columns
        validator: GeneValidator instance (creates new if None)

    Returns:
        DataFrame with validation columns added
    """
    if validator is None:
        validator = GeneValidator()

    import pandas as pd

    if genes_df.empty:
        return genes_df

    # Validate each gene-variant pair
    results = []
    for _, row in genes_df.iterrows():
        gene = str(row.get("gene", "")).strip()
        variant = str(row.get("variant", "")).strip()

        result = validator.validate_gene_variant(gene, variant)
        results.append(result)

    # Add validation columns
    genes_df = genes_df.copy()
    genes_df["gene_valid"] = [r.is_valid_gene for r in results]
    genes_df["variant_valid"] = [r.is_valid_variant for r in results]
    genes_df["validation_confidence"] = [r.confidence_score for r in results]
    genes_df["validation_source"] = [r.validation_source for r in results]
    genes_df["validation_suggestions"] = [
        ", ".join(r.suggestions) if r.suggestions else "" for r in results
    ]

    return genes_df
