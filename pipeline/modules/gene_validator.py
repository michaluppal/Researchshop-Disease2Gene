"""
Gene and Variant Validation Module

This module provides heuristics for validating gene and variant names extracted by AI models
against known databases of human genes and mutations using real APIs.
"""

import difflib
import json
import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from . import config

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
class TableCitationResult:
    """Result of table-cell citation validation."""
    field_name: str
    table_label: str
    matched_row_idx: int
    gene_found_in_row: bool
    values_matched: List[str]
    values_missing: List[str]
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
        self.session.headers.update({'User-Agent': 'ResearchShop/1.0'})
        # Cache for gene lookups to avoid repeated API calls
        self._gene_cache = {}
        # Load local HGNC database for fast lookups
        self._local_gene_db = self._load_local_hgnc_database()
        self._local_alias_index = self._build_local_alias_index()

    def _load_local_hgnc_database(self) -> Dict[str, Dict]:
        """Load local HGNC gene database for fast validation."""
        from datetime import date

        hgnc_path = Path(__file__).parent.parent / 'data' / 'reference' / 'hgnc_genes.json'
        meta_path = hgnc_path.with_name('hgnc_genes_meta.json')

        # Check snapshot staleness
        if meta_path.exists():
            try:
                with open(meta_path, 'r') as f:
                    meta = json.load(f)
                snapshot_date = date.fromisoformat(meta.get('snapshot_date', '2000-01-01'))
                age_days = (date.today() - snapshot_date).days
                if age_days > 365:
                    logger.warning(
                        f"HGNC snapshot is {age_days} days old (since {snapshot_date}). "
                        "Run pipeline/scripts/refresh_hgnc.py to update."
                    )
            except Exception:
                pass

        if hgnc_path.exists():
            try:
                with open(hgnc_path, 'r') as f:
                    gene_db = json.load(f)
                logger.info(f"Loaded {len(gene_db)} genes from local HGNC database")
                return gene_db
            except Exception as e:
                logger.warning(f"Failed to load local HGNC database: {e}")
        else:
            logger.warning(f"Local HGNC database not found at {hgnc_path}")

        return {}

    def _build_local_alias_index(self) -> Dict[str, str]:
        """
        Build alias -> canonical symbol index from local HGNC snapshot.
        """
        idx: Dict[str, str] = {}
        db = self._local_gene_db or {}
        for sym_u, info in db.items():
            idx[sym_u.upper()] = sym_u
            aliases = (info.get('alias_symbol') or info.get('aliases') or [])
            prevs = (info.get('prev_symbol') or info.get('prev_symbols') or [])
            for token in list(aliases) + list(prevs):
                t = str(token or '').strip().upper()
                if t and t not in idx:
                    idx[t] = sym_u
        return idx

    def get_gene_biotype(self, symbol: str) -> str:
        """Return HGNC locus_type for a resolved gene symbol."""
        info = self._local_gene_db.get(symbol.upper(), {})
        return info.get('locus_type', 'unknown')

    @staticmethod
    def _norm_token(token: str) -> str:
        return re.sub(r'[^A-Z0-9]', '', (token or '').upper())

    @lru_cache(maxsize=5000)
    def resolve_gene_symbol(self, candidate: str) -> Tuple[Optional[str], str]:
        """
        Resolve a candidate gene/protein label to canonical HGNC symbol.
        Returns (symbol, source) where source indicates resolution path.
        """
        c = (candidate or '').strip()
        if not c:
            return None, "empty"

        c_u = c.upper()
        # Direct canonical symbol
        if self._local_gene_db and c_u in self._local_gene_db:
            return c_u, "local_symbol"

        # Local alias/previous-symbol map
        aliased = self._local_alias_index.get(c_u)
        if aliased:
            return aliased, "local_alias"

        # Normalized alias match (strip punctuation/hyphens)
        c_norm = self._norm_token(c)
        if c_norm:
            for alias_u, sym_u in self._local_alias_index.items():
                if self._norm_token(alias_u) == c_norm:
                    return sym_u, "local_alias_norm"

        # Remote HGNC fetch fallbacks (authoritative)
        for field in ("symbol", "alias_symbol", "prev_symbol"):
            try:
                url = f"https://rest.genenames.org/fetch/{field}/{c}"
                response = self.session.get(url, headers={'Accept': 'application/json'}, timeout=8)
                if response.status_code != 200:
                    continue
                payload = response.json()
                docs = payload.get('response', {}).get('docs', [])
                if docs:
                    sym = (docs[0].get('symbol') or '').upper()
                    if sym:
                        return sym, f"hgnc_{field}"
            except Exception as e:
                logger.debug(f"HGNC {field} lookup failed for '{c}': {e}")
                continue

        # Remote MyGene alias/symbol resolution (accept only exact symbol/alias matches)
        try:
            url = "https://mygene.info/v3/query"
            params = {
                'q': f'{c} AND taxid:9606',
                'fields': 'symbol,alias,name',
                'species': 'human',
                'size': 10,
            }
            response = self.session.get(url, params=params, timeout=8)
            if response.status_code == 200:
                data = response.json()
                hits = data.get('hits') or []
                for hit in hits:
                    sym = (hit.get('symbol') or '').upper()
                    if not sym:
                        continue
                    if self._norm_token(sym) == c_norm:
                        return sym, "mygene_symbol"
                    aliases = hit.get('alias') or []
                    if isinstance(aliases, str):
                        aliases = [aliases]
                    for alias in aliases:
                        if self._norm_token(str(alias)) == c_norm:
                            return sym, "mygene_alias"
        except Exception as e:
            logger.debug(f"MyGene.info query failed for '{c}': {e}")

        return None, "unresolved"

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
                'symbol': gene_info.get('symbol'),
                'name': gene_info.get('name'),
                'source': 'HGNC_local'
            }

        # Fallback to API if local database unavailable or gene not found
        try:
            url = f"https://rest.genenames.org/fetch/symbol/{gene_symbol}"
            headers = {'Accept': 'application/json'}
            response = self.session.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('response', {}).get('numFound', 0) > 0:
                    docs = data['response']['docs']
                    if docs:
                        return {
                            'symbol': docs[0].get('symbol'),
                            'name': docs[0].get('name'),
                            'hgnc_id': docs[0].get('hgnc_id'),
                            'source': 'HGNC_API'
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
                'q': f'symbol:{gene_symbol} AND taxid:9606',  # Human genes only
                'fields': 'symbol,name,entrezgene,ensembl.gene',
                'species': 'human',
                'size': 1
            }
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('total', 0) > 0 and data.get('hits'):
                    hit = data['hits'][0]
                    return {
                        'symbol': hit.get('symbol'),
                        'name': hit.get('name'),
                        'entrez_id': hit.get('entrezgene'),
                        'source': 'MyGene.info'
                    }
            time.sleep(0.1)  # Rate limiting
        except Exception as e:
            logger.debug(f"MyGene.info lookup failed for {gene_symbol}: {e}")
        return None

    def _compile_variant_patterns(self) -> Dict[str, re.Pattern]:
        """Compile regex patterns for common variant formats."""
        return {
            # Single amino acid substitutions
            'hgvs_protein': re.compile(r'^p\.[A-Z][a-z]{2}\d+(?:[A-Z][a-z]{2}|[*])?$'),
            'hgvs_protein_short': re.compile(r'^p\.[A-Z]\d+[A-Z*]?$'),
            'amino_acid_substitution': re.compile(r'^[A-Z]\d+[A-Z*]$'),

            # Coding and genomic changes (including splicing/UTRs)
            'hgvs_coding': re.compile(r'^c\.[*+-]?\d+(?:[+-]\d+)?(?:_[*+-]?\d+(?:[+-]\d+)?)?[a-zA-Z]>[a-zA-Z]$'),
            'hgvs_genomic': re.compile(r'^g\.\d+(?:_\d+)?[a-zA-Z]>[a-zA-Z]$'),
            'splice_site': re.compile(r'^IVS\d+[+-]\d+$'),

            # Frameshifts
            'frameshift_hgvs': re.compile(r'^p\.(?:[A-Z][a-z]{2}|[A-Z])\d+(?:(?:[A-Z][a-z]{2}|[A-Z])fs\*?\d*|fs\*?\d*)$'),
            'frameshift_simple': re.compile(r'^fs\d*$'),

            # Exon level events
            'exon_deletion': re.compile(r'^exon\s+\d+(?:-\d+)?\s+del(?:etion)?$', re.IGNORECASE),
            'exon_insertion': re.compile(r'^exon\s+\d+(?:-\d+)?\s+ins(?:ertion)?$', re.IGNORECASE),

            # Duplications, Deletions, Insertions, Indels
            # Note: order matters in Python 3.7+. deletion_insertion must precede deletion.
            'duplication': re.compile(r'^(?:[cpg]\.)?(?:[*+-]?\d+(?:_[*+-]?\d+)?|(?:[A-Z][a-z]{2}|[A-Z])\d+(?:_\d+)?)dup[a-zA-Z0-9]*$|^dup$'),
            'deletion_insertion': re.compile(r'^(?:[cpg]\.)?(?:[*+-]?\d+(?:_[*+-]?\d+)?|(?:[A-Z][a-z]{2}|[A-Z])\d+(?:_\d+)?)delins[a-zA-Z0-9]*$|^delins$'),
            'deletion': re.compile(r'^(?:[cpg]\.)?(?:[*+-]?\d+(?:_[*+-]?\d+)?|(?:[A-Z][a-z]{2}|[A-Z])\d+(?:_\d+)?)del[a-zA-Z0-9]*$|^del\d*$'),
            'insertion': re.compile(r'^(?:[cpg]\.)?(?:[*+-]?\d+(?:_[*+-]?\d+)?|(?:[A-Z][a-z]{2}|[A-Z])\d+(?:_\d+)?)ins[a-zA-Z0-9]*$|^ins$'),

            # Legacy/other
            'dbsnp_rsid': re.compile(r'^rs\d+$', re.IGNORECASE),
            'nonsense': re.compile(r'^X\d+$'),

            # Structural variants / CNV (AUDIT A4 YELLOW #3 — 2026-03-02)
            'copy_number_state': re.compile(r'^CN=\d+$'),                              # CN=3, CN=0
            'translocation': re.compile(                                                 # t(9;22), t(9;22)(q34;q11.2)
                r'^t\(\d+;(?:\d+|[XY])\)(?:\([a-zA-Z0-9.]+;[a-zA-Z0-9.]+\))?$',
                re.IGNORECASE
            ),
            'cnv_cytogenetic': re.compile(                                               # del(5q), dup(17p11.2)
                r'^(?:del|dup)\((?:\d+|[XY])(?:[pq][pq\d.]*)?\)$',
                re.IGNORECASE
            ),
            'inversion_cytogenetic': re.compile(                                         # inv(3)(q21q26.2)
                r'^inv\((?:\d+|[XY])\)(?:\([a-zA-Z0-9.]+\))?$',
                re.IGNORECASE
            ),
            'inversion_genomic': re.compile(r'^[gch]\.\d+_\d+inv$', re.IGNORECASE),    # g.1000_2000inv
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
                    if not hasattr(self, '_alias_index'):
                        alias_index = {}
                        for sym_u, info in self._local_gene_db.items():
                            # Support both old field names (aliases/prev_symbols)
                            # and new field names (alias_symbol/prev_symbol)
                            for a in (info.get('alias_symbol') or info.get('aliases') or []):
                                alias_index.setdefault(a.upper(), sym_u)
                            for p in (info.get('prev_symbol') or info.get('prev_symbols') or []):
                                alias_index.setdefault(p.upper(), sym_u)
                        self._alias_index = alias_index
                    target = self._alias_index.get(gene_upper)
                    if target:
                        gene_upper = target
                except Exception as e:
                    logger.warning(f"Failed to build alias index: {e}")

        # Check cache first
        if gene_upper in self._gene_cache:
            cached = self._gene_cache[gene_upper]
            return cached['valid'], cached['source'], cached.get('suggestions', [])

        # Try HGNC first (authoritative source)
        hgnc_result = self._validate_gene_hgnc(gene_upper)
        if hgnc_result:
            self._gene_cache[gene_upper] = {'valid': True, 'source': 'HGNC', 'data': hgnc_result}
            return True, "HGNC", []

        # Fallback to MyGene.info
        mygene_result = self._validate_gene_mygene(gene_upper)
        if mygene_result:
            self._gene_cache[gene_upper] = {'valid': True, 'source': 'MyGene.info', 'data': mygene_result}
            return True, "MyGene.info", []

        # Try fuzzy matching for common misspellings
        suggestions = self._fuzzy_match_gene(gene_upper)
        self._gene_cache[gene_upper] = {'valid': False, 'source': 'not_found', 'suggestions': suggestions}

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
            params = {
                'q': gene_name,
                'fields': 'symbol',
                'species': 'human',
                'size': 3
            }
            response = self.session.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                if data.get('hits'):
                    return [hit.get('symbol', '') for hit in data['hits'] if hit.get('symbol')]
        except Exception as e:
            logger.debug(f"Fuzzy match failed for {gene_name}: {e}")

        return []

    def validate_gene_variant(self, gene: str, variant: str = "") -> GeneValidationResult:
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
            confidence = 1.0 if is_valid_gene else 0.0

        validation_source = f"{gene_source}"
        if variant:
            validation_source += f" + variant_{variant_source}"

        # Resolve canonical symbol for biotype/organism checks
        resolved_symbol, _ = self.resolve_gene_symbol(gene) if gene else (None, "empty")

        # Detect potential murine-convention symbols (Title case: Brca1, Tp53)
        gene_stripped = (gene or '').strip()
        if resolved_symbol and gene_stripped and gene_stripped != resolved_symbol:
            if len(gene_stripped) >= 2 and gene_stripped[0].isupper() and any(c.islower() for c in gene_stripped[1:3]):
                validation_source += ' | potential_murine_symbol'

        return GeneValidationResult(
            gene=gene,
            variant=variant,
            is_valid_gene=is_valid_gene,
            is_valid_variant=is_valid_variant if variant else True,  # True if no variant specified
            confidence_score=confidence,
            validation_source=validation_source,
            suggestions=gene_suggestions
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
                gene = assoc.get('gene', '')
                variant = assoc.get('variant', '')
                # Normalize placeholders
                if isinstance(variant, str) and variant.upper() in {"N/A", "NA", "NONE"}:
                    variant = ''
            else:
                gene, variant = assoc

            result = self.validate_gene_variant(gene, variant)
            results.append(result)
            logger.info(f"Validated gene variant: gene_valid={result.is_valid_gene}, "
                       f"variant_valid={result.is_valid_variant}, confidence={result.confidence_score:.2f}")

        return results

    def filter_valid_associations(self, associations: List,
                                   min_confidence: float = 0.7) -> List:
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
                logger.warning(f"Filtered out gene variant (confidence: {result.confidence_score:.2f} < {min_confidence})")

        return valid_associations


# Citation validation functions
def _extract_numbers(text: str) -> List[str]:
    """Extract standalone numbers (integers, floats) from text."""
    return re.findall(r'\b\d+(?:\.\d+)?\b', text)


def validate_citations(ai_response: Dict[str, str], paper_text: str, gene_symbol: str = "") -> List[CitationValidationResult]:
    """
    Validate that citations provided by AI actually exist in the paper.

    Args:
        ai_response: Dictionary mapping field names to their values with citations
        paper_text: Full text of the paper
        gene_symbol: The target gene symbol for contextual enforcement

    Returns:
        List of CitationValidationResult objects
    """
    results = []

    for field_name, response_text in ai_response.items():
        # Extract citation from response (assumes format like: "Answer. Citation: 'quoted text'")
        citation = _extract_citation_from_response(response_text)

        if citation:
            exists, ratio, reason = _citation_exists_in_paper(citation, paper_text, gene_symbol)
            confidence = _calculate_citation_confidence(citation, paper_text, exists, ratio)

            results.append(CitationValidationResult(
                field_name=field_name,
                provided_citation=citation,
                citation_exists=exists,
                confidence_score=confidence,
                validation_details=reason
            ))

            if not exists:
                logger.warning(f"Citation validation FAILED for {field_name}: {reason} (Citation: '{citation}')")
        else:
            results.append(CitationValidationResult(
                field_name=field_name,
                provided_citation="",
                citation_exists=False,
                confidence_score=0.0,
                validation_details="No citation provided in response"
            ))

    return results


def _extract_citation_from_response(response_text: str) -> str:
    """Extract citation text from AI response."""
    if not response_text:
        return ""

    # Try to find citation patterns
    patterns = [
        r'Citation:\s*["\']([^"\']+)["\']',  # Citation: "text"
        r'Citation:\s*(.+?)(?:\n|$)',  # Citation: text
        r'\[Citation:\s*([^\]]+)\]',  # [Citation: text]
        r'"([^"]{20,})"',  # Any quoted text > 20 chars
    ]

    for pattern in patterns:
        match = re.search(pattern, response_text, re.IGNORECASE)
        if match:
            citation = match.group(1).strip()
            if len(citation) > 10:  # Minimum length for meaningful citation
                return citation

    return ""


def _normalize_unicode_slashes(text: str) -> str:
    """Replace typographic slash variants and LaTeX character commands with their plain equivalents.

    Handles two classes of encoding artifact found in biomedical PDFs:
    - Unicode lookalike slashes (U+2044 fraction slash, etc.) emitted by typesetting tools
    - LaTeX math commands (\\upmu, \\mu, etc.) that the LLM transcribes from training memory
      when the paper text contains the Unicode character (μ) but the model outputs \\upmu g/l
    """
    # Unicode slash variants → ASCII solidus
    text = text.replace('\u2044', '/').replace('\u2215', '/').replace('\uff0f', '/').replace('\u29f8', '/')
    # LaTeX Greek / math commands → Unicode equivalents common in biomedical units
    text = text.replace('\\upmu', 'μ').replace('\\mu', 'μ')
    text = text.replace('\\upalpha', 'α').replace('\\alpha', 'α')
    text = text.replace('\\upbeta', 'β').replace('\\beta', 'β')
    text = text.replace('\\upgamma', 'γ').replace('\\gamma', 'γ')
    text = text.replace('\\pm', '±')
    text = text.replace('\\geq', '≥').replace('\\leq', '≤')
    text = text.replace('\\times', '×')
    # ASCII "mu " before unit characters → μ
    # Handles LLM output like "671.0 mu g/l" when paper has "671.0 μg/l".
    # Regex is safe: \bmu\s+ at a word boundary before g/l/m/u only matches unit prefixes.
    import re
    text = re.sub(r'\bmu\s+([gGlLmMuU])', r'μ\1', text)
    # Unify the two Unicode micro/mu variants: U+00B5 MICRO SIGN (µ) → U+03BC GREEK SMALL LETTER MU (μ)
    text = text.replace('\u00b5', 'μ')
    return text


def _normalize_citation_drift(text: str) -> str:
    """
    Normalise formatting-drift artefacts so SequenceMatcher isn't fooled by
    typeset variants of the same quote. Applied symmetrically on both citation
    and paper_text before word-level matching (F10a).

    Order matters:
    1. Soft hyphen (U+00AD) removal — runs first so broken words re-merge
       before any other pass touches them.
    2. Line-break hyphenation: (\\w)-\\n(\\w) → \\1\\2. Must run before any
       downstream .split() call.
    3. Non-breaking hyphen (U+2011) → ASCII hyphen.
    4. En-dash (U+2013) + em-dash (U+2014) → ASCII hyphen.
    5. Common f-ligatures: U+FB01 ﬁ → "fi", U+FB02 ﬂ → "fl",
       U+FB00 ﬀ → "ff", U+FB03 ﬃ → "ffi", U+FB04 ﬄ → "ffl".
    """
    if not text:
        return text
    # 1. Soft hyphen removal (first)
    text = text.replace("\u00AD", "")
    # 2. Line-break hyphenation
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # 3. Non-breaking hyphen
    text = text.replace("\u2011", "-")
    # 4. En-dash + em-dash unification
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    # 5. Ligatures
    text = (text
        .replace("\ufb00", "ff")
        .replace("\ufb01", "fi")
        .replace("\ufb02", "fl")
        .replace("\ufb03", "ffi")
        .replace("\ufb04", "ffl"))
    return text


def _citation_exists_in_paper(citation: str, paper_text: str, gene_symbol: str = "", gene_aliases: List[str] = None, tables: List[Dict[str, Any]] = None) -> Tuple[bool, float, str]:
    """
    Check if citation text exists in the paper securely using dense matching, numerical consistency, and gene context.
    Returns (exists, matching_ratio, detailed_reason)

    gene_aliases: additional pre-normalization labels to check in the gene context step
    (e.g. for NPPB, pass gene_aliases=["BNP"] since the paper uses the alias, not the canonical symbol).
    """
    if not citation or not paper_text:
        return False, 0.0, "Empty citation or paper"

    # Normalize Unicode slash variants and formatting-drift artefacts (F10a) before any matching.
    # Applied symmetrically on both sides so SequenceMatcher isn't fooled by typeset variants.
    citation = _normalize_citation_drift(_normalize_unicode_slashes(citation))
    paper_text = _normalize_citation_drift(_normalize_unicode_slashes(paper_text))

    # Normalize texts
    citation_norm = ' '.join(citation.lower().split())
    paper_norm_lower = paper_text.lower()
    paper_norm_lower = ' '.join(paper_norm_lower.split())

    cit_words = citation_norm.split()
    paper_words = paper_norm_lower.split()

    best_ratio = 0.0
    match_start_char = -1
    match_end_char = -1

    # Track prose matching result — None means checks still passing
    prose_failure: Optional[Tuple[bool, float, str]] = None

    # 1. Exact Match Check
    exact_idx = paper_norm_lower.find(citation_norm)
    if exact_idx != -1:
        best_ratio = 1.0
        match_start_char = exact_idx
        match_end_char = exact_idx + len(citation_norm)
    else:
        # 2. Dense Matching Fallback (Sliding Window on Words)
        if len(cit_words) < 5:
            prose_failure = (False, 0.0, "No exact match for short citation")

        if prose_failure is None:
            window_size = len(cit_words) + 3
            matcher = difflib.SequenceMatcher(None, cit_words)

            best_idx_words = -1

            # Step size to slide window to quickly find overlapping candidate regions
            step = max(1, len(cit_words) // 2)
            cit_set = set(cit_words)

            for i in range(0, len(paper_words) - len(cit_words) + step, step):
                window = paper_words[i:i + window_size]
                common = cit_set & set(window)
                if len(common) / len(cit_set) < 0.6:
                    continue

                # Finer search in the neighborhood
                start_j = max(0, i - step)
                end_j = min(len(paper_words) - len(cit_words) + 1, i + step)
                for j in range(start_j, end_j):
                    exact_window = paper_words[j:j+window_size]
                    matcher.set_seq2(exact_window)
                    ratio = matcher.ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_idx_words = j

            threshold = getattr(config, "CITATION_DENSE_MATCH_MIN_RATIO", 0.85)
            if best_ratio < threshold:
                if best_ratio < 0.6:
                    msg = f"No similar text in paper (best ratio: {best_ratio:.2f})"
                else:
                    msg = (
                        f"Near-miss match (ratio {best_ratio:.2f} < threshold "
                        f"{threshold:.2f}) — likely formatting drift"
                    )
                prose_failure = (False, best_ratio, msg)
            else:
                # Find approximate char index of the matched window
                anchor_snippet = ' '.join(paper_words[max(0, best_idx_words):best_idx_words+min(3, len(cit_words))])
                match_start_char = paper_norm_lower.find(anchor_snippet)
                if match_start_char == -1:
                    match_start_char = 0
                    match_end_char = len(paper_norm_lower)
                else:
                    match_end_char = match_start_char + len(' '.join(paper_words[best_idx_words:best_idx_words+window_size]))

    if prose_failure is None:
        # 3. Strict Numerical Enforcement
        cit_numbers = _extract_numbers(citation)
        if cit_numbers:
            # Extract a slightly larger window from the original text (e.g. paragraph bounds)
            # +/- 500 characters
            context_start = max(0, match_start_char - 500)
            context_end = min(len(paper_text), match_end_char + 500)
            context_str = paper_text[context_start:context_end]

            # Find numbers in context
            context_numbers = _extract_numbers(context_str)
            context_numbers_set = set(context_numbers)

            for num in cit_numbers:
                if num not in context_numbers_set:
                    prose_failure = (False, best_ratio, f"Numerical mismatch: '{num}' not found in matching paragraph")
                    break

    if prose_failure is None:
        # 4. Contextual Gene Enforcement
        # Check canonical symbol + all raw pre-normalization labels (e.g. BNP for NPPB).
        # Papers often use aliases (BNP, IFN-gamma, M-CSF) rather than HGNC canonical symbols.
        symbols_to_check: List[str] = []
        if gene_symbol:
            symbols_to_check.append(gene_symbol)
        if gene_aliases:
            symbols_to_check.extend(a for a in gene_aliases if a and a != gene_symbol)

        if symbols_to_check:
            # Use a wide window (±1500 chars) so that gene names mentioned a few paragraphs
            # before/after the cited sentence are still captured — e.g. a conclusion sentence
            # adjacent to a BNP-discussion paragraph that is >500 chars away.
            context_start = max(0, match_start_char - 1500)
            context_end = min(len(paper_text), match_end_char + 1500)
            context_str_lower = paper_text[context_start:context_end].lower()

            found_symbol = False
            for sym in symbols_to_check:
                sym_lower = sym.lower()
                escaped = re.escape(sym_lower)
                if re.search(r'\b' + escaped + r'\b', context_str_lower):
                    found_symbol = True
                    break
                # Also check without hyphens
                if re.search(r'\b' + escaped.replace("-", "") + r'\b', context_str_lower.replace("-", "")):
                    found_symbol = True
                    break

            if not found_symbol:
                all_syms = ", ".join(f"'{s}'" for s in symbols_to_check)
                prose_failure = (False, best_ratio, f"Gene symbols ({all_syms}) not found in matching paragraph context")

    if prose_failure is None:
        return True, best_ratio, "Match found and constraints verified"

    # Table-cell fallback: when prose matching fails and tables are available
    if tables and gene_symbol:
        table_result = validate_table_citation(citation, tables, gene_symbol, gene_aliases)
        if table_result and table_result.confidence_score >= 0.7:
            return True, table_result.confidence_score, f"table_match:{table_result.table_label}"

    return prose_failure


def _calculate_citation_confidence(citation: str, paper_text: str, exists: bool, match_ratio: float = 0.0) -> float:
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

    # Boost based on density match
    if match_ratio >= 0.99:
        confidence += 0.1

    return min(confidence, 1.0)


# Table-cell citation validation

def _find_gene_in_table_rows(
    table_dict: Dict[str, Any],
    gene_symbol: str,
    gene_aliases: List[str] = None,
) -> List[int]:
    """Return row indices where gene or alias appears in any cell."""
    matching_rows: List[int] = []
    symbols = [gene_symbol.lower()]
    if gene_aliases:
        symbols.extend(a.lower() for a in gene_aliases if a)

    rows = table_dict.get("rows", [])
    for row_idx, row in enumerate(rows):
        for cell in row:
            cell_lower = str(cell).lower()
            for sym in symbols:
                if sym and sym in cell_lower:
                    matching_rows.append(row_idx)
                    break
            else:
                continue
            break

    return matching_rows


def validate_table_citation(
    citation_text: str,
    tables: List[Dict[str, Any]],
    gene_symbol: str,
    gene_aliases: List[str] = None,
) -> Optional[TableCitationResult]:
    """Gene-anchored row matching for table-based citation verification.

    Strategy:
    1. For each table, find rows where gene_symbol or any alias appears in any cell
    2. For matching rows, extract numbers from citation_text (reuse _extract_numbers pattern)
    3. Check if those numbers appear in the same row's cells
    4. Return best match (highest confidence) or None

    Scoring:
    - Gene + all numbers match in same row -> confidence 1.0
    - Gene matches but some numbers missing -> confidence 0.7
    - Gene not found in any table -> return None
    """
    if not citation_text or not tables or not gene_symbol:
        return None

    cit_numbers = _extract_numbers(citation_text)
    best_result: Optional[TableCitationResult] = None

    for table in tables:
        label = table.get("label", table.get("table_id", "unknown"))
        gene_rows = _find_gene_in_table_rows(table, gene_symbol, gene_aliases)
        if not gene_rows:
            continue

        rows = table.get("rows", [])
        for row_idx in gene_rows:
            if row_idx >= len(rows):
                continue
            row = rows[row_idx]
            # Collect all numbers in this row's cells
            row_text = " ".join(str(cell) for cell in row)
            row_numbers_set = set(_extract_numbers(row_text))

            matched = [n for n in cit_numbers if n in row_numbers_set]
            missing = [n for n in cit_numbers if n not in row_numbers_set]

            if cit_numbers:
                if not missing:
                    score = 1.0
                else:
                    score = 0.7
            else:
                # No numbers in citation but gene found in table row
                score = 0.7

            detail_parts = [f"gene in row {row_idx} of {label}"]
            if matched:
                detail_parts.append(f"matched values: {matched}")
            if missing:
                detail_parts.append(f"missing values: {missing}")

            if best_result is None or score > best_result.confidence_score:
                best_result = TableCitationResult(
                    field_name="",
                    table_label=label,
                    matched_row_idx=row_idx,
                    gene_found_in_row=True,
                    values_matched=matched,
                    values_missing=missing,
                    confidence_score=score,
                    validation_details="; ".join(detail_parts),
                )
                # Short-circuit on perfect match
                if score >= 1.0:
                    return best_result

    return best_result


# Context window validation
class ContextWindowValidator:
    """Validates that paper content fits within model context windows."""

    # Token limits for Gemini models (approximate, with safety margin)
    GEMINI_FLASH_LIMIT = 1000000  # 1M tokens
    GEMINI_PRO_LIMIT = 2000000    # 2M tokens
    SAFETY_MARGIN = 0.9  # Use 90% of limit to be safe

    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        Estimate token count for text.
        Rough approximation: ~1.3 tokens per word for English biomedical text.
        Scientific papers with technical terms tokenize at higher ratios than casual text.
        """
        if not text:
            return 0

        # Word-based estimation calibrated for biomedical text
        words = len(text.split())
        estimated_tokens = int(words * 1.3)

        return estimated_tokens

    @staticmethod
    def check_context_fit(text: str, model_name: str = "flash") -> Tuple[bool, int, int]:
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
            limit = int(ContextWindowValidator.GEMINI_FLASH_LIMIT * ContextWindowValidator.SAFETY_MARGIN)
        else:
            limit = int(ContextWindowValidator.GEMINI_PRO_LIMIT * ContextWindowValidator.SAFETY_MARGIN)

        fits = estimated_tokens <= limit

        return fits, estimated_tokens, limit

    @staticmethod
    def truncate_text(text: str, model_name: str = "flash", preserve_sections: bool = True) -> str:
        """
        Truncate text to fit within context window.

        Args:
            text: Text to truncate
            model_name: "flash" or "pro"
            preserve_sections: Try to preserve complete sections

        Returns:
            Truncated text
        """

        fits, current_tokens, limit = ContextWindowValidator.check_context_fit(text, model_name)

        if fits:
            return text

        logger.warning(f"Paper exceeds context limit ({current_tokens} > {limit} tokens). Truncating...")

        if preserve_sections:
            return ContextWindowValidator._truncate_preserve_sections(text, limit)
        else:
            # Simple truncation
            target_words = int(limit / 0.75)
            words = text.split()
            return ' '.join(words[:target_words])

    @staticmethod
    def _truncate_preserve_sections(text: str, token_limit: int) -> str:
        """Truncate while trying to preserve complete sections."""
        sections = ContextWindowValidator._split_into_sections(text)

        truncated_sections = []
        current_tokens = 0

        for section_text in sections:
            section_tokens = ContextWindowValidator.estimate_token_count(section_text)
            if current_tokens + section_tokens <= token_limit:
                truncated_sections.append(section_text)
                current_tokens += section_tokens
            else:
                break

        return '\n\n'.join(truncated_sections)

    @staticmethod
    def _split_into_sections(text: str) -> List[str]:
        """Split text into logical sections."""
        # Split on common section headers
        section_patterns = [
            r'\n\s*(?:Abstract|Introduction|Methods|Results|Discussion|Conclusion|References)[\s:]+',
            r'\n\s*\d+\.\s+[A-Z][^.\n]+\n',  # Numbered sections
            r'\n\n+',  # Double line breaks
        ]

        sections = [text]
        for pattern in section_patterns:
            new_sections = []
            for section in sections:
                parts = re.split(pattern, section)
                new_sections.extend([p for p in parts if p.strip()])
            sections = new_sections

        return sections

    @staticmethod
    def validate_paper_context(paper_text: str) -> Dict[str, dict]:
        """
        Validate paper text against both model context windows.

        Args:
            paper_text: Full paper text to validate

        Returns:
            Dictionary with validation results for both flash and pro models
        """
        results = {}

        # Check flash model
        flash_fits, flash_tokens, flash_limit = ContextWindowValidator.check_context_fit(paper_text, "flash")
        results["flash_model"] = {
            "fits": flash_fits,
            "estimated_tokens": flash_tokens,
            "recommendation": f"Text fits within gemini-2.5-flash context limit ({flash_tokens:,} < {flash_limit:,} tokens)" if flash_fits else f"Text exceeds gemini-2.5-flash context limit ({flash_tokens:,} > {flash_limit:,} tokens). Consider truncation."
        }

        # Check pro model
        pro_fits, pro_tokens, pro_limit = ContextWindowValidator.check_context_fit(paper_text, "pro")
        results["pro_model"] = {
            "fits": pro_fits,
            "estimated_tokens": pro_tokens,
            "recommendation": f"Text fits within gemini-2.5-pro context limit ({pro_tokens:,} < {pro_limit:,} tokens)" if pro_fits else f"Text exceeds gemini-2.5-pro context limit ({pro_tokens:,} > {pro_limit:,} tokens). Consider truncation."
        }

        return results


def validate_paper_context_fit(paper_text: str, model_name: str = "flash") -> Dict[str, object]:
    """
    Legacy function - validates paper fits within model context window.

    Args:
        paper_text: Paper text to validate
        model_name: "flash" or "pro"

    Returns:
        Dictionary with validation results
    """
    fits, tokens, limit = ContextWindowValidator.check_context_fit(paper_text, model_name)

    result = {
        'fits': fits,
        'estimated_tokens': tokens,
        'token_limit': limit,
        'utilization': tokens / limit if limit > 0 else 0,
        'needs_truncation': not fits
    }

    if not fits:
        logger.warning(f"Paper text ({tokens} tokens) exceeds {model_name} context limit ({limit} tokens)")
    else:
        logger.info(f"Paper text fits within {model_name} context: {tokens}/{limit} tokens ({result['utilization']:.1%})")

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


    if genes_df.empty:
        return genes_df

    # Validate each gene-variant pair
    results = []
    for _, row in genes_df.iterrows():
        gene = str(row.get('gene', '')).strip()
        variant = str(row.get('variant', '')).strip()

        result = validator.validate_gene_variant(gene, variant)
        results.append(result)

    # Add validation columns
    genes_df = genes_df.copy()
    genes_df['gene_valid'] = [r.is_valid_gene for r in results]
    genes_df['variant_valid'] = [r.is_valid_variant for r in results]
    genes_df['validation_confidence'] = [r.confidence_score for r in results]
    genes_df['validation_source'] = [r.validation_source for r in results]
    genes_df['validation_suggestions'] = [', '.join(r.suggestions) if r.suggestions else '' for r in results]
    genes_df['Gene Biotype'] = [
        validator.get_gene_biotype(str(row.get('gene', '')).strip())
        for _, row in genes_df.iterrows()
    ]

    return genes_df
