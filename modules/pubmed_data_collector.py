# modules/pubmed_data_collector.py

import time
import logging
import re
import requests
from Bio import Entrez, Medline
from tqdm import tqdm
import xml.etree.ElementTree as ET
from . import config

# Configure logging and Entrez
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s",
)

# Note: Entrez.email is set in run_local.py after config is loaded
# Setting it here at import time would use None since config hasn't been set yet
# The functions below will work correctly when Entrez.email is set before they're called


def apply_publication_type_filter(query: str) -> str:
    """
    Applies publication type filters to exclude non-research papers.

    FIX #1: Publication Type Filtering
    Excludes reviews, meta-analyses, editorials, and other non-primary research.
    Expected impact: 40% waste reduction.
    """
    if not getattr(config, "ENABLE_PUBLICATION_TYPE_FILTER", True):
        return query

    # Use publication types from config
    excluded_types = getattr(config, "EXCLUDED_PUBLICATION_TYPES", [])

    if not excluded_types:
        return query

    # Build NOT clause with OR for multiple types
    # PubMed syntax: (query) NOT (Type1[PT] OR Type2[PT] OR Type3[PT])
    # Note: PubMed's [Publication Type] tag handles multi-word types automatically
    # DO NOT quote them - quoting breaks the query syntax
    or_clauses = " OR ".join(
        [f"{pub_type}[Publication Type]" for pub_type in excluded_types]
    )

    # Wrap original query in parentheses if needed and append filters
    if query.strip():
        enhanced_query = f"({query}) NOT ({or_clauses})"
    else:
        enhanced_query = f"NOT ({or_clauses})"

    logging.info(
        f"Applied publication type filter: excluding {len(excluded_types)} types"
    )
    logging.info(f"Enhanced query: {enhanced_query}")
    return enhanced_query


def search_pubmed(query_to_search, max_results):
    """
    Searches PubMed using a direct API request.
    Now includes publication type filtering to exclude non-research papers.
    """
    # Apply publication type filter before searching
    filtered_query = apply_publication_type_filter(query_to_search)
    logging.info(f"Searching PubMed with filtered query: {filtered_query}")

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": filtered_query,
        "retmax": max_results,
        "usehistory": "y",
        "sort": config.PUBMED_SORT,
    }
    # Only add API key if it's available
    if config.ENTREZ_API_KEY:
        params["api_key"] = config.ENTREZ_API_KEY

    try:
        response = requests.get(base_url, params=params)
        # Log the actual URL being requested for debugging
        logging.debug(f"PubMed API URL: {response.url}")
        response.raise_for_status()
        root = ET.fromstring(response.content)

        # Check for errors in the response
        error_element = root.find("ErrorList")
        if error_element is not None:
            error_msg = error_element.findtext("Error")
            if error_msg:
                logging.warning(
                    f"PubMed search returned error: {error_msg} for query '{filtered_query}'"
                )

        # Check the Count element to see total results (even if IdList is empty)
        count_element = root.find("Count")
        total_count = count_element.text if count_element is not None else "unknown"
        logging.info(
            f"PubMed search returned total count: {total_count} for query: {filtered_query}"
        )

        id_list_element = root.find("IdList")
        if id_list_element is not None:
            pmids = [id_element.text for id_element in id_list_element.findall("Id")]
            logging.info(
                f"PubMed search returned {len(pmids)} PMIDs (requested max: {max_results}) for query: {filtered_query}"
            )
            if len(pmids) == 0 and int(total_count) > 0:
                logging.warning(
                    f"PubMed returned count={total_count} but no PMIDs in IdList - possible query syntax issue"
                )
            return pmids
        else:
            logging.warning(
                f"PubMed search returned no IdList for query: {filtered_query} (total count: {total_count})"
            )
            return []
    except requests.exceptions.RequestException as e:
        logging.error(f"PubMed search request failed: {e}")
        raise e
    except Exception as e:
        logging.error(f"PubMed search parsing failed: {e}")
        return []


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
    for i in tqdm(
        range(0, len(paper_ids), batch_size),
        desc="Fetching paper details",
        unit="batch",
    ):
        batch_pmids = paper_ids[i : i + batch_size]

        # Create batch request
        post_data = {
            "db": "pubmed",
            "id": ",".join(batch_pmids),  # Comma-separated PMIDs for batch request
            "rettype": "medline",
            "retmode": "text",
        }
        # Only add API key if it's available
        if config.ENTREZ_API_KEY:
            post_data["api_key"] = config.ENTREZ_API_KEY

        try:
            response = requests.post(base_url, data=post_data)
            response.raise_for_status()

            # Parse all records in the batch
            records = list(Medline.parse(response.text.splitlines()))

            for record in records:
                pmid = record.get("PMID", "")
                if pmid and "TI" in record:  # Only include records with titles
                    paper_info[pmid] = {
                        "title": record.get("TI", "No Title"),
                        "authors": record.get("AU", []),
                        "year": (
                            match.group(1)
                            if (
                                match := re.search(r"\b(\d{4})\b", record.get("DP", ""))
                            )
                            else "N/A"
                        ),
                        "journal": record.get("JT", "N/A"),
                        "affiliations": record.get("AD", []),
                        "abstract": record.get("AB", "No abstract available"),
                        "pub_types": record.get("PT", []),
                        "doi": record.get("LID", "").replace(" [doi]", "") if "[doi]" in record.get("LID", "") else "",
                        "PMID": pmid,
                    }
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch details for batch {i//batch_size + 1}: {e}")
        except Exception as e:
            logging.error(f"Error processing batch {i//batch_size + 1}: {e}")

        # Rate limiting: wait between requests to avoid hitting NCBI limits
        time.sleep(0.4)  # 2.5 requests per second max

    return paper_info


def fetch_semantic_citation_counts(pmids):
    """
    Fetch citation counts via Semantic Scholar REST to avoid loop patching.
    """
    if not pmids:
        return {}
    logging.info(f"Fetching Semantic Scholar citation counts for {len(pmids)} PMIDs.")
    citation_counts = {}
    for pmid in tqdm(pmids, desc="Fetching Semantic Citations"):
        try:
            r = requests.get(
                f"https://api.semanticscholar.org/graph/v1/paper/PMID:{pmid}",
                params={"fields": "citationCount"},
                timeout=15,
            )
            if r.ok:
                data = r.json()
                citation_counts[pmid] = int(data.get("citationCount", 0))
            else:
                citation_counts[pmid] = 0
        except Exception as e:
            logging.error(f"Failed to fetch citation for PMID {pmid}: {e}")
            citation_counts[pmid] = 0
    return citation_counts
