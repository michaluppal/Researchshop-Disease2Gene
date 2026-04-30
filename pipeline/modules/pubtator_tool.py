#!/usr/bin/env python3
"""
PubTator Integration Module for Hybrid Pipeline

This module integrates PubTator Central as a gene/variant extraction tool,
providing high-precision NER as a foundation for LLM-based relationship
and attribute extraction.

Architecture:
1. PubTator provides initial gene/variant mentions (high precision)
2. LLM extracts additional genes PubTator missed (high recall)
3. LLM extracts relationships and user-defined attributes
4. NCBI Gene provides rich metadata for all extracted genes

API Reference: https://www.ncbi.nlm.nih.gov/research/pubtator3/api
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from . import config

logger = logging.getLogger(__name__)

# PubTator3 API endpoints
PUBTATOR_API_BASE = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
PUBTATOR_EXPORT_ENDPOINT = f"{PUBTATOR_API_BASE}/publications/export/biocjson"

# NCBI Gene API
NCBI_GENE_API = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class NCBIRateLimitError(Exception):
    """Raised when NCBI keeps returning 429 after bounded retries."""


@dataclass
class PubTatorGene:
    """Gene annotation from PubTator."""
    symbol: str
    ncbi_gene_id: Optional[str] = None
    text_mentions: List[str] = field(default_factory=list)
    locations: List[Dict] = field(default_factory=list)
    confidence: float = 1.0  # PubTator doesn't provide confidence, assume high
    source: str = "pubtator"

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "ncbi_gene_id": self.ncbi_gene_id,
            "text_mentions": self.text_mentions,
            "source": self.source
        }


@dataclass
class PubTatorVariant:
    """Variant annotation from PubTator."""
    text: str
    variant_type: str  # SNP, mutation, etc.
    rsid: Optional[str] = None
    hgvs: Optional[str] = None
    gene_id: Optional[str] = None
    locations: List[Dict] = field(default_factory=list)
    source: str = "pubtator"

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "text": self.text,
            "variant_type": self.variant_type,
            "rsid": self.rsid,
            "hgvs": self.hgvs,
            "gene_id": self.gene_id,
            "source": self.source
        }


@dataclass
class NCBIGeneMetadata:
    """Rich metadata from NCBI Gene database."""
    gene_id: str
    symbol: str
    full_name: str
    aliases: List[str] = field(default_factory=list)
    chromosome: Optional[str] = None
    map_location: Optional[str] = None
    gene_type: Optional[str] = None
    summary: Optional[str] = None
    organism: str = "Homo sapiens"
    mim_id: Optional[str] = None  # OMIM ID
    ensembl_id: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "gene_id": self.gene_id,
            "symbol": self.symbol,
            "full_name": self.full_name,
            "aliases": self.aliases[:5] if self.aliases else [],  # Limit aliases for output
            "chromosome": self.chromosome,
            "gene_type": self.gene_type
        }


class PubTatorTool:
    """
    PubTator integration for hybrid gene extraction pipeline.

    Usage:
        tool = PubTatorTool()
        genes, variants = tool.extract_from_pmid("12345678")
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "ResearchShop/1.0 (gene-extraction-pipeline)"
        })
        self._batch_size = getattr(config, 'PUBTATOR_BATCH_SIZE', 10)

    def extract_from_pmid(self, pmid: str) -> Tuple[List[PubTatorGene], List[PubTatorVariant]]:
        """
        Extract genes and variants from a paper using PubTator.

        Args:
            pmid: PubMed ID

        Returns:
            Tuple of (genes, variants)
        """
        genes = []
        variants = []

        try:
            url = f"{PUBTATOR_EXPORT_ENDPOINT}?pmids={pmid}"
            response = self._session.get(url, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Handle PubTator3 response format
            if isinstance(data, dict) and "PubTator3" in data:
                documents = data["PubTator3"]
            elif isinstance(data, list):
                documents = data
            else:
                documents = [data]

            for doc in documents:
                doc_genes, doc_variants = self._parse_document(doc)
                genes.extend(doc_genes)
                variants.extend(doc_variants)

        except requests.RequestException as e:
            logger.warning(f"PubTator API error for PMID {pmid}: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"PubTator JSON parse error for PMID {pmid}: {e}")

        return genes, variants

    def extract_from_pmids(self, pmids: List[str], batch_size: Optional[int] = None) -> Dict[str, Tuple[List[PubTatorGene], List[PubTatorVariant]]]:
        """
        Extract genes and variants from multiple papers.

        Args:
            pmids: List of PubMed IDs
            batch_size: Number of PMIDs per API request (default from config)

        Returns:
            Dict mapping PMID -> (genes, variants)
        """
        if batch_size is None:
            batch_size = self._batch_size

        results = {}
        total_batches = (len(pmids) + batch_size - 1) // batch_size

        logger.info(f"PubTator: Extracting genes from {len(pmids)} papers in {total_batches} batches")

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i+batch_size]
            pmid_str = ",".join(batch)
            batch_num = (i // batch_size) + 1

            try:
                url = f"{PUBTATOR_EXPORT_ENDPOINT}?pmids={pmid_str}"
                response = self._session.get(url, timeout=60)
                response.raise_for_status()

                data = response.json()

                if isinstance(data, dict) and "PubTator3" in data:
                    documents = data["PubTator3"]
                elif isinstance(data, list):
                    documents = data
                else:
                    documents = [data]

                for doc in documents:
                    pmid = str(doc.get("pmid", doc.get("id", "")))
                    if not pmid:
                        _id = doc.get("_id", "")
                        if "|" in _id:
                            pmid = _id.split("|")[0]

                    if pmid:
                        genes, variants = self._parse_document(doc)
                        results[pmid] = (genes, variants)

                missing_in_batch = [p for p in batch if p not in results]
                if missing_in_batch:
                    logger.warning(
                        f"PubTator batch {batch_num}/{total_batches}: {len(missing_in_batch)} PMID(s) "
                        f"not returned by API (not indexed or unrecognized format): {missing_in_batch}"
                    )
                logger.debug(f"PubTator batch {batch_num}/{total_batches}: processed {len(batch)} PMIDs")

            except Exception as e:
                logger.warning(f"PubTator batch {batch_num} error: {e}")

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"PubTator: Completed extraction for {len(results)}/{len(pmids)} papers")
        return results

    def _parse_document(self, doc: Dict) -> Tuple[List[PubTatorGene], List[PubTatorVariant]]:
        """Parse a PubTator BioC JSON document."""
        genes = {}  # symbol -> PubTatorGene
        variants = []

        for passage in doc.get("passages", []):
            for annotation in passage.get("annotations", []):
                infons = annotation.get("infons", {})
                ann_type = infons.get("type", "").lower()
                text = annotation.get("text", "")
                location = annotation.get("locations", [{}])[0] if annotation.get("locations") else {}

                if ann_type == "gene":
                    # Extract gene information
                    gene_id = infons.get("identifier", infons.get("normalized_id", ""))
                    symbol = infons.get("name", text).upper()

                    if symbol:
                        if symbol not in genes:
                            genes[symbol] = PubTatorGene(
                                symbol=symbol,
                                ncbi_gene_id=str(gene_id) if gene_id else None,
                                text_mentions=[text],
                                locations=[location] if location else []
                            )
                        else:
                            genes[symbol].text_mentions.append(text)
                            if location:
                                genes[symbol].locations.append(location)

                elif ann_type in ("variant", "snp", "mutation"):
                    # Extract variant information
                    rsid = None
                    hgvs = None
                    gene_id = None

                    # Try to extract rsID
                    if "rsid" in infons:
                        rsid = infons["rsid"]
                    elif text.startswith("rs"):
                        rsid = text

                    # Try to extract HGVS
                    normalized = infons.get("normalized", "")
                    if normalized:
                        # Handle both string and list formats
                        if isinstance(normalized, list):
                            normalized = normalized[0] if normalized else ""
                        if isinstance(normalized, str) and not normalized.startswith("rs"):
                            hgvs = normalized

                    # Try to extract associated gene
                    gene_id = infons.get("gene_id", infons.get("CorrespondingGene", ""))

                    variant = PubTatorVariant(
                        text=text,
                        variant_type=ann_type,
                        rsid=rsid,
                        hgvs=hgvs,
                        gene_id=str(gene_id) if gene_id else None,
                        locations=[location] if location else []
                    )
                    variants.append(variant)

        return list(genes.values()), variants


class NCBIGeneTool:
    """
    NCBI Gene database integration for rich gene metadata.

    Provides detailed gene information including:
    - Official symbol and full name
    - Aliases (for matching non-standard nomenclature)
    - Chromosomal location
    - Gene type (protein-coding, etc.)
    - Summary/function description
    - Cross-references (OMIM, Ensembl)

    Example page: https://www.ncbi.nlm.nih.gov/gene/925 (CD8A)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(config, 'NCBI_API_KEY', None)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "ResearchShop/1.0 (gene-metadata-extraction)"
        })
        self._cache: Dict[str, NCBIGeneMetadata] = {}
        self._gene_id_negative_cache: Set[str] = set()
        self._symbol_cache: Dict[str, Optional[NCBIGeneMetadata]] = {}
        self._symbol_negative_cache: Set[str] = set()
        self._last_request_at = 0.0
        self._request_interval_seconds = 0.11 if self.api_key else 0.34

    def _throttle_request(self) -> None:
        elapsed = time.time() - self._last_request_at
        delay = self._request_interval_seconds - elapsed
        if delay > 0:
            time.sleep(delay)

    def _request_json(
        self,
        endpoint: str,
        params: Dict[str, Any],
        *,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Call NCBI EUtils with request-level throttling and bounded 429 backoff."""
        params = dict(params)
        if self.api_key:
            params["api_key"] = self.api_key

        url = f"{NCBI_GENE_API}/{endpoint}"
        for attempt in range(max_retries + 1):
            self._throttle_request()
            response = self._session.get(url, params=params, timeout=30)
            self._last_request_at = time.time()

            if response.status_code == 429 and attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 0.5 * (2 ** attempt)
                except (TypeError, ValueError):
                    delay = 0.5 * (2 ** attempt)
                time.sleep(min(max(delay, self._request_interval_seconds), 5.0))
                continue
            if response.status_code == 429:
                raise NCBIRateLimitError("NCBI Gene API rate limited after retries")

            response.raise_for_status()
            return response.json()

        return {}

    def get_gene_metadata(self, gene_id: str) -> Optional[NCBIGeneMetadata]:
        """
        Fetch metadata for a gene from NCBI Gene database.

        Args:
            gene_id: NCBI Gene ID (e.g., "925" for CD8A)

        Returns:
            NCBIGeneMetadata or None if not found
        """
        # Check cache first
        if gene_id in self._cache:
            return self._cache[gene_id]
        if gene_id in self._gene_id_negative_cache:
            return None

        try:
            # Use ESummary for basic info
            params = {
                "db": "gene",
                "id": gene_id,
                "retmode": "json"
            }
            data = self._request_json("esummary.fcgi", params)

            if "result" not in data or gene_id not in data["result"]:
                self._gene_id_negative_cache.add(gene_id)
                return None

            gene_data = data["result"][gene_id]

            # Check for errors in response
            if "error" in gene_data:
                self._gene_id_negative_cache.add(gene_id)
                return None

            # Extract aliases
            aliases = []
            if "otheraliases" in gene_data and gene_data["otheraliases"]:
                aliases = [a.strip() for a in gene_data["otheraliases"].split(",")]
            if "otherdesignations" in gene_data and gene_data["otherdesignations"]:
                aliases.extend([d.strip() for d in gene_data["otherdesignations"].split("|")])

            metadata = NCBIGeneMetadata(
                gene_id=gene_id,
                symbol=gene_data.get("name", ""),
                full_name=gene_data.get("description", ""),
                aliases=aliases,
                chromosome=gene_data.get("chromosome", ""),
                map_location=gene_data.get("maplocation", ""),
                gene_type=gene_data.get("genetictype", ""),
                summary=gene_data.get("summary", ""),
                organism=gene_data.get("organism", {}).get("scientificname", "Homo sapiens") if isinstance(gene_data.get("organism"), dict) else "Homo sapiens"
            )

            # Cache result
            self._cache[gene_id] = metadata
            return metadata

        except NCBIRateLimitError as e:
            logger.warning(f"NCBI Gene API rate limited for ID {gene_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"NCBI Gene API error for ID {gene_id}: {e}")
            return None

    def get_gene_by_symbol(self, symbol: str) -> Optional[NCBIGeneMetadata]:
        """
        Search for a gene by symbol and return metadata.

        Args:
            symbol: Gene symbol (e.g., "CD8A", "BRCA1")

        Returns:
            NCBIGeneMetadata or None if not found
        """
        symbol_key = str(symbol or "").strip().upper()
        if not symbol_key:
            return None
        if symbol_key in self._symbol_cache:
            return self._symbol_cache[symbol_key]
        if symbol_key in self._symbol_negative_cache:
            return None

        # Check cache by symbol
        for cached in self._cache.values():
            if cached.symbol.upper() == symbol_key:
                self._symbol_cache[symbol_key] = cached
                return cached

        try:
            # Use ESearch to find gene ID
            params = {
                "db": "gene",
                "term": f"{symbol}[Gene Name] AND Homo sapiens[Organism]",
                "retmode": "json"
            }
            data = self._request_json("esearch.fcgi", params)

            if "esearchresult" not in data or not data["esearchresult"].get("idlist"):
                self._symbol_cache[symbol_key] = None
                self._symbol_negative_cache.add(symbol_key)
                return None

            gene_id = data["esearchresult"]["idlist"][0]
            meta = self.get_gene_metadata(gene_id)
            self._symbol_cache[symbol_key] = meta
            if meta is None:
                self._symbol_negative_cache.add(symbol_key)
            return meta

        except NCBIRateLimitError as e:
            logger.warning(f"NCBI Gene search rate limited for symbol {symbol}: {e}")
            return None
        except Exception as e:
            logger.warning(f"NCBI Gene search error for symbol {symbol}: {e}")
            return None

    def enrich_genes(self, genes: List[PubTatorGene]) -> Dict[str, NCBIGeneMetadata]:
        """
        Enrich a list of genes with NCBI Gene metadata.

        Args:
            genes: List of PubTatorGene objects

        Returns:
            Dict mapping symbol -> NCBIGeneMetadata
        """
        metadata = {}

        for gene in genes:
            if gene.ncbi_gene_id and ";" not in gene.ncbi_gene_id:
                # Use gene ID if available and not compound
                meta = self.get_gene_metadata(gene.ncbi_gene_id)
            else:
                # Fall back to symbol search
                meta = self.get_gene_by_symbol(gene.symbol)

            if meta:
                metadata[gene.symbol] = meta

        return metadata

    def enrich_gene_symbols(
        self,
        symbols: List[str],
        symbol_gene_ids: Optional[Dict[str, str]] = None,
    ) -> Dict[str, NCBIGeneMetadata]:
        """
        Enrich a list of gene symbols with NCBI Gene metadata.

        Args:
            symbols: List of gene symbol strings

        Returns:
            Dict mapping symbol -> NCBIGeneMetadata
        """
        metadata = {}
        symbol_gene_ids_norm = {
            str(symbol or "").strip().upper(): str(gene_id or "").strip()
            for symbol, gene_id in (symbol_gene_ids or {}).items()
            if str(symbol or "").strip() and str(gene_id or "").strip()
        }

        for symbol in symbols:
            symbol_key = str(symbol or "").strip().upper()
            gene_id = symbol_gene_ids_norm.get(symbol_key)
            if gene_id and ";" not in gene_id:
                meta = self.get_gene_metadata(gene_id)
                if meta is not None:
                    self._symbol_cache[symbol_key] = meta
                else:
                    meta = self.get_gene_by_symbol(symbol)
            else:
                meta = self.get_gene_by_symbol(symbol)
            if meta:
                metadata[symbol] = meta

        return metadata


class HybridExtractionResult:
    """Result from hybrid PubTator + LLM extraction."""

    def __init__(self, pmid: str):
        self.pmid = pmid
        self.pubtator_genes: List[PubTatorGene] = []
        self.pubtator_variants: List[PubTatorVariant] = []
        self.llm_genes: List[str] = []  # All genes found by LLM
        self.llm_variants: List[str] = []
        self.gene_metadata: Dict[str, NCBIGeneMetadata] = {}
        self.attributes: Dict[str, Dict] = {}  # gene -> attributes from LLM

    @property
    def pubtator_gene_symbols(self) -> Set[str]:
        """Gene symbols from PubTator."""
        return {g.symbol.upper() for g in self.pubtator_genes}

    @property
    def llm_gene_symbols(self) -> Set[str]:
        """Gene symbols from LLM."""
        return {g.upper() for g in self.llm_genes}

    @property
    def all_genes(self) -> Set[str]:
        """All unique genes from both sources (union)."""
        return self.pubtator_gene_symbols | self.llm_gene_symbols

    @property
    def pubtator_only_genes(self) -> Set[str]:
        """Genes found only by PubTator."""
        return self.pubtator_gene_symbols - self.llm_gene_symbols

    @property
    def llm_only_genes(self) -> Set[str]:
        """Genes found only by LLM."""
        return self.llm_gene_symbols - self.pubtator_gene_symbols

    @property
    def overlap_genes(self) -> Set[str]:
        """Genes found by both PubTator and LLM."""
        return self.pubtator_gene_symbols & self.llm_gene_symbols

    def get_gene_source(self, gene_symbol: str) -> str:
        """Get the source(s) that found this gene."""
        gene_upper = gene_symbol.upper()
        in_pubtator = gene_upper in self.pubtator_gene_symbols
        in_llm = gene_upper in self.llm_gene_symbols

        if in_pubtator and in_llm:
            return "both"
        elif in_pubtator:
            return "pubtator"
        elif in_llm:
            return "llm"
        else:
            return "unknown"

    def get_ncbi_gene_id(self, gene_symbol: str) -> Optional[str]:
        """Get NCBI Gene ID for a gene symbol."""
        gene_upper = gene_symbol.upper()

        # Check PubTator genes first (they have IDs)
        for g in self.pubtator_genes:
            if g.symbol.upper() == gene_upper and g.ncbi_gene_id:
                return g.ncbi_gene_id

        # Check metadata
        if gene_upper in self.gene_metadata:
            return self.gene_metadata[gene_upper].gene_id

        return None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "pmid": self.pmid,
            "pubtator_genes": [g.to_dict() for g in self.pubtator_genes],
            "pubtator_variants": [v.to_dict() for v in self.pubtator_variants],
            "llm_genes": self.llm_genes,
            "llm_variants": self.llm_variants,
            "all_genes": list(self.all_genes),
            "gene_count": len(self.all_genes),
            "pubtator_contribution": len(self.pubtator_only_genes),
            "llm_contribution": len(self.llm_only_genes),
            "overlap": len(self.overlap_genes),
            "gene_metadata": {
                symbol: meta.to_dict()
                for symbol, meta in self.gene_metadata.items()
            },
            "attributes": self.attributes
        }


# Convenience functions for quick extraction
def extract_with_pubtator(pmid: str) -> Tuple[List[PubTatorGene], List[PubTatorVariant]]:
    """Quick extraction using PubTator."""
    tool = PubTatorTool()
    return tool.extract_from_pmid(pmid)


def extract_batch_with_pubtator(pmids: List[str]) -> Dict[str, Tuple[List[PubTatorGene], List[PubTatorVariant]]]:
    """Batch extraction using PubTator."""
    tool = PubTatorTool()
    return tool.extract_from_pmids(pmids)


def get_gene_info(symbol_or_id: str) -> Optional[NCBIGeneMetadata]:
    """Quick gene metadata lookup."""
    tool = NCBIGeneTool()
    if symbol_or_id.isdigit():
        return tool.get_gene_metadata(symbol_or_id)
    else:
        return tool.get_gene_by_symbol(symbol_or_id)


if __name__ == "__main__":
    # Test the tools
    logging.basicConfig(level=logging.INFO)

    print("Testing PubTator Tool...")
    pt_tool = PubTatorTool()
    genes, variants = pt_tool.extract_from_pmid("21533171")  # ITPKC paper
    print(f"  Found {len(genes)} genes, {len(variants)} variants")
    for g in genes[:5]:
        print(f"    - {g.symbol} (ID: {g.ncbi_gene_id})")

    print("\nTesting NCBI Gene Tool...")
    ncbi_tool = NCBIGeneTool()

    # Test with CD8A (Gene ID: 925)
    meta = ncbi_tool.get_gene_metadata("925")
    if meta:
        print(f"  CD8A: {meta.full_name}")
        print(f"  Aliases: {', '.join(meta.aliases[:5])}")
        print(f"  Chromosome: {meta.chromosome}")

    # Test symbol search
    meta = ncbi_tool.get_gene_by_symbol("BRCA1")
    if meta:
        print(f"\n  BRCA1: {meta.full_name}")
        print(f"  Gene ID: {meta.gene_id}")
