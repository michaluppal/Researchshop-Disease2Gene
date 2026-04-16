# modules/pubmed_data_collector.py

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from io import StringIO
from typing import List, Optional, Tuple, Union

import requests
from Bio import Entrez, Medline
from tqdm import tqdm

from . import config


@dataclass
class SearchMetadata:
    """Forensic audit record for a PubMed search query."""
    query_original: str
    query_effective: str
    max_results_requested: int
    pmids_returned: int
    oa_filter_applied: bool
    pub_type_filter_applied: bool
    timestamp_utc: str

# Configure logging and Entrez
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s')
Entrez.email = config.ENTREZ_EMAIL
if config.ENTREZ_API_KEY:
    Entrez.api_key = config.ENTREZ_API_KEY


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [str(value)]


def _extract_year(record):
    date_candidates = [
        record.get("DP", ""),
        record.get("EDAT", ""),
        record.get("PHST", ""),
        record.get("DEP", ""),
        record.get("PDAT", ""),
    ]
    for candidate in date_candidates:
        if isinstance(candidate, list):
            candidate = " ".join(str(x) for x in candidate if x)
        match = re.search(r"\b(19|20)\d{2}\b", str(candidate))
        if match:
            return match.group(0)
    return "N/A"


def _extract_doi(record):
    # MEDLINE commonly stores DOI in AID entries as "<doi> [doi]"
    for aid in _as_list(record.get("AID", [])):
        m = re.match(r"(.+)\s+\[doi\]$", str(aid).strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    for lid in _as_list(record.get("LID", [])):
        m = re.match(r"(.+)\s+\[doi\]$", str(lid).strip(), flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _normalize_pubmed_record(record):
    pmid = str(record.get("PMID", "")).strip()
    title = str(record.get("TI", "")).strip() or "No Title"
    authors = [a.strip() for a in _as_list(record.get("AU", [])) if str(a).strip()]
    affiliations = [a.strip() for a in _as_list(record.get("AD", [])) if str(a).strip()]
    abstract = str(record.get("AB", "")).strip() or "No abstract available"
    journal = str(record.get("JT", "")).strip() or "N/A"
    year = _extract_year(record)
    doi = _extract_doi(record)

    warnings = []
    if not pmid:
        warnings.append("missing_pmid")
    if title == "No Title":
        warnings.append("missing_title")
    if year == "N/A":
        warnings.append("missing_year")
    if journal == "N/A":
        warnings.append("missing_journal")
    if not authors:
        warnings.append("missing_authors")
    if abstract == "No abstract available":
        warnings.append("missing_abstract")

    checks = 5
    passed = 0
    if title != "No Title":
        passed += 1
    if year != "N/A":
        passed += 1
    if journal != "N/A":
        passed += 1
    if authors:
        passed += 1
    if abstract != "No abstract available":
        passed += 1

    return {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": journal,
        "affiliations": affiliations,
        "abstract": abstract,
        "PMID": pmid,
        "doi": doi,
        "_metadata_warnings": warnings,
        "_metadata_completeness": round(passed / checks, 2),
    }

def apply_publication_type_filter(query: str) -> str:
    """
    Applies publication type filters to exclude non-research papers.

    FIX #1: Publication Type Filtering
    Excludes reviews, meta-analyses, editorials, and other non-primary research.
    Expected impact: 40% waste reduction.
    """
    if not getattr(config, 'ENABLE_PUBLICATION_TYPE_FILTER', True):
        return query

    excluded_types = getattr(config, 'EXCLUDED_PUBLICATION_TYPES', [
        'Review', 'Meta-Analysis', 'Systematic Review',
        'Editorial', 'Comment', 'Letter', 'News',
        'Practice Guideline', 'Guideline', 'Clinical Trial Protocol',
        'Consensus Development Conference', 'Consensus Development Conference, NIH'
    ])

    if not excluded_types:
        return query

    # Build NOT clauses for each excluded type
    not_clauses = ' AND '.join([f'NOT {pub_type}[Publication Type]' for pub_type in excluded_types])

    # Wrap original query in parentheses if needed and append filters
    if query.strip():
        enhanced_query = f"({query}) AND {not_clauses}"
    else:
        enhanced_query = not_clauses

    logging.info(f"Applied publication type filter: excluding {len(excluded_types)} types")
    return enhanced_query

def apply_oa_filter(query: str) -> str:
    """
    Restrict PubMed results to papers with free full text available at NCBI.

    Appends the 'loattrfull text' subset filter which NCBI uses to flag
    articles where the full text is accessible for free (PMC OA, author
    manuscripts, etc.).  Controlled by config.ENABLE_OA_FILTER.
    """
    if not getattr(config, 'ENABLE_OA_FILTER', True):
        return query

    oa_clause = '"loattrfull text"[sb]'
    if query.strip():
        enhanced = f"({query}) AND {oa_clause}"
    else:
        enhanced = oa_clause

    logging.info("Applied open-access full text filter to PubMed query")
    return enhanced

def search_pubmed(query_to_search, max_results, return_metadata=False):
    """
    Searches PubMed using a direct API request.
    Now includes publication type filtering to exclude non-research papers.

    Args:
        query_to_search: The PubMed query string.
        max_results: Maximum number of PMIDs to return.
        return_metadata: If True, return (pmids, SearchMetadata) instead of just pmids.

    Returns:
        List of PMID strings, or Tuple[List[str], SearchMetadata] if return_metadata=True.
    """
    oa_filter_applied = getattr(config, 'ENABLE_OA_FILTER', True)
    pub_type_filter_applied = getattr(config, 'ENABLE_PUBLICATION_TYPE_FILTER', True)

    # Apply publication type filter before searching
    filtered_query = apply_publication_type_filter(query_to_search)
    # Apply open-access full text filter
    filtered_query = apply_oa_filter(filtered_query)

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': filtered_query,
        'retmax': max_results,
        'usehistory': 'y',
        'sort': config.PUBMED_SORT,
    }
    # Only add API key if it's available
    if config.ENTREZ_API_KEY:
        params['api_key'] = config.ENTREZ_API_KEY

    pmids = []
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        id_list_element = root.find('IdList')
        if id_list_element is not None:
            pmids = [id_element.text for id_element in id_list_element.findall('Id')]
    except requests.exceptions.RequestException as e:
        logging.error(f"PubMed search request failed: {e}")
        raise e

    if return_metadata:
        metadata = SearchMetadata(
            query_original=query_to_search,
            query_effective=filtered_query,
            max_results_requested=max_results,
            pmids_returned=len(pmids),
            oa_filter_applied=oa_filter_applied,
            pub_type_filter_applied=pub_type_filter_applied,
            timestamp_utc=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        )
        return pmids, metadata

    return pmids

def search_pubmed_by_author(author_name, max_results=200):
    """Searches PubMed for papers by a specific author."""
    query = f"{author_name}[Author]"
    return search_pubmed(query, max_results)

def fetch_paper_details(paper_ids, batch_size=50):
    """Fetches detailed information for a list of PMIDs using batched requests for better performance."""
    if not paper_ids:
        return {}
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    paper_info = {}

    # Process in batches for better performance
    for i in tqdm(range(0, len(paper_ids), batch_size), desc="Fetching paper details", unit="batch"):
        batch_pmids = paper_ids[i:i + batch_size]

        # Create batch request
        post_data = {
            'db': 'pubmed',
            'id': ','.join(batch_pmids),  # Comma-separated PMIDs for batch request
            'rettype': 'medline',
            'retmode': 'text'
        }
        # Only add API key if it's available
        if config.ENTREZ_API_KEY:
            post_data['api_key'] = config.ENTREZ_API_KEY

        try:
            response = requests.post(base_url, data=post_data)
            response.raise_for_status()

            # Parse all records in the batch using StringIO (splitlines() merges PMIDs!)
            records = list(Medline.parse(StringIO(response.text)))

            for record in records:
                normalized = _normalize_pubmed_record(record)
                pmid = normalized.get("PMID", "")
                if pmid:
                    paper_info[pmid] = normalized
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch details for batch {i//batch_size + 1}: {e}")
        except Exception as e:
            logging.error(f"Error processing batch {i//batch_size + 1}: {e}")

        # Rate limiting: wait between requests to avoid hitting NCBI limits
        time.sleep(0.4)  # 2.5 requests per second max

    return paper_info


def _extract_icite_citation_count(record):
    """Extract citation count from iCite payload across known field variants."""
    direct_fields = [
        'citedByPmidCount',  # newer field naming used in docs
        'citation_count',    # current API payload field
        'cited_by_count',
    ]
    for field in direct_fields:
        value = record.get(field)
        if isinstance(value, (int, float)):
            return int(value)

    # Some payloads expose cited PMID lists
    cited_by = record.get('cited_by')
    if isinstance(cited_by, list):
        return len(cited_by)

    cited_by_year = record.get('citedByPmidsByYear')
    if isinstance(cited_by_year, list):
        return len(cited_by_year)

    return None


def fetch_icite_citation_counts(pmids, batch_size=200):
    """
    Fetch citation counts from NIH iCite (primary source for PMID-native biomedical papers).
    Returns dict: PMID -> citation_count
    """
    if not pmids:
        return {}

    citation_counts = {}
    base_url = 'https://icite.od.nih.gov/api/pubs'
    normalized_pmids = [str(p).strip() for p in pmids if str(p).strip()]

    logging.info(f"Fetching iCite citation counts for {len(normalized_pmids)} PMIDs.")
    for i in range(0, len(normalized_pmids), batch_size):
        batch = normalized_pmids[i:i + batch_size]
        try:
            response = requests.get(
                base_url,
                params={'pmids': ','.join(batch)},
                timeout=max(config.REQUEST_TIMEOUT, 20),
            )
            response.raise_for_status()
            payload = response.json()
            records = payload.get('data', [])
            for record in records:
                pmid = str(record.get('pmid') or record.get('_id') or '').strip()
                count = _extract_icite_citation_count(record)
                if pmid and count is not None:
                    citation_counts[pmid] = int(count)
        except Exception as e:
            logging.warning(f"iCite citation batch fetch failed ({i}-{i + len(batch)}): {e}")
        time.sleep(0.1)

    return citation_counts


def _fetch_semantic_citation_records(pmids):
    """
    Fetch Semantic Scholar citation records.
    Returns dict: PMID -> {'ok': bool, 'count': int|None}
    """
    if not pmids:
        return {}

    results = {}
    logging.info(f"Fetching Semantic Scholar citation counts for {len(pmids)} PMIDs.")
    for pmid in tqdm(pmids, desc="Fetching Semantic Citations"):
        pmid = str(pmid).strip()
        try:
            r = requests.get(
                f'https://api.semanticscholar.org/graph/v1/paper/PMID:{pmid}',
                params={'fields': 'citationCount'},
                timeout=15,
            )
            if r.ok:
                data = r.json()
                results[pmid] = {'ok': True, 'count': int(data.get('citationCount', 0))}
            elif r.status_code == 429:
                logging.warning("Semantic Scholar rate limit hit, pausing 5s...")
                time.sleep(5)
                results[pmid] = {'ok': False, 'count': None}
            else:
                results[pmid] = {'ok': False, 'count': None}
        except Exception as e:
            logging.error(f"Failed to fetch citation for PMID {pmid}: {e}")
            results[pmid] = {'ok': False, 'count': None}
        time.sleep(0.2)  # ~5 req/sec
    return results


def fetch_citation_counts_with_fallback(pmids):
    """
    Citation source strategy:
      1) iCite (primary)
      2) Semantic Scholar (fallback)

    Returns dict: PMID -> {
      'count': int,
      'source': 'icite' | 'semantic_scholar' | 'none',
      'retrieved_at': ISO8601 UTC,
      'icite_count': int|None,
      'semantic_scholar_count': int|None,
    }
    """
    if not pmids:
        return {}

    normalized_pmids = [str(p).strip() for p in pmids if str(p).strip()]
    retrieved_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    icite_counts = fetch_icite_citation_counts(normalized_pmids)
    unresolved = [pmid for pmid in normalized_pmids if pmid not in icite_counts]
    semantic_records = _fetch_semantic_citation_records(unresolved) if unresolved else {}

    out = {}
    for pmid in normalized_pmids:
        icite_count = icite_counts.get(pmid)
        semantic_record = semantic_records.get(pmid, {'ok': False, 'count': None})
        semantic_count = semantic_record.get('count') if semantic_record.get('ok') else None

        if icite_count is not None:
            out[pmid] = {
                'count': int(icite_count),
                'source': 'icite',
                'retrieved_at': retrieved_at,
                'icite_count': int(icite_count),
                'semantic_scholar_count': semantic_count,
            }
        elif semantic_record.get('ok'):
            out[pmid] = {
                'count': int(semantic_record.get('count') or 0),
                'source': 'semantic_scholar',
                'retrieved_at': retrieved_at,
                'icite_count': None,
                'semantic_scholar_count': int(semantic_record.get('count') or 0),
            }
        else:
            out[pmid] = {
                'count': 0,
                'source': 'none',
                'retrieved_at': retrieved_at,
                'icite_count': None,
                'semantic_scholar_count': None,
            }

    icite_used = sum(1 for v in out.values() if v.get('source') == 'icite')
    semantic_used = sum(1 for v in out.values() if v.get('source') == 'semantic_scholar')
    none_used = sum(1 for v in out.values() if v.get('source') == 'none')
    logging.info(
        f"Citation sources: iCite={icite_used}, SemanticScholar={semantic_used}, none={none_used}"
    )
    return out


def fetch_semantic_citation_counts(pmids):
    """
    Backward-compatible helper returning only Semantic Scholar citation counts.
    """
    records = _fetch_semantic_citation_records(pmids)
    return {str(p): int(v.get('count') or 0) for p, v in records.items()}
