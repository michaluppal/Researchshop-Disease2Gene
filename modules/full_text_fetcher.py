# modules/full_text_fetcher.py

import time
import logging
import pickle
import gzip
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import trafilatura
import re
from bs4 import BeautifulSoup
from typing import Union, Dict, Any, List, Tuple, Optional
from tqdm import tqdm
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass
import json
import io
import concurrent.futures
import subprocess
import sys

from . import config
from Bio import Entrez

logger = logging.getLogger(__name__)

_DOMAIN_FAILURE_CACHE: Dict[str, Dict[str, Any]] = {}
_PLAYWRIGHT_VERIFIED = False
_PLAYWRIGHT_AVAILABLE = False


def _get_domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _domain_timeout_ms(domain: str) -> int:
    """Return navigation timeout per domain (ms)."""
    # Faster timeouts for known redirect/access hubs
    if any(
        k in domain for k in ["linkinghub.elsevier", "retrieve/pii", "prolekare.cz"]
    ):
        return 90000
    if "doi.org" in domain:
        return 60000
    # Heavy JS sites may need longer
    if any(
        k in domain for k in ["tandfonline.com", "ascopubs.org", "annualreviews.org"]
    ):
        return 110000
    # Default
    return 60000


def _note_domain_failure(domain: str, reason: str) -> None:
    if not domain:
        return
    info = _DOMAIN_FAILURE_CACHE.get(domain) or {"count": 0, "reasons": set()}
    info["count"] += 1
    try:
        info["reasons"].add(reason)
    except Exception:
        pass
    _DOMAIN_FAILURE_CACHE[domain] = info


def _verify_playwright_installation() -> bool:
    """
    Verify that Playwright browsers are properly installed.
    Returns True if Playwright is available and Chromium can be launched, False otherwise.
    """
    global _PLAYWRIGHT_VERIFIED, _PLAYWRIGHT_AVAILABLE

    if _PLAYWRIGHT_VERIFIED:
        return _PLAYWRIGHT_AVAILABLE

    _PLAYWRIGHT_VERIFIED = True

    try:
        # Check if playwright is importable
        from playwright.sync_api import sync_playwright

        # Try to verify browser installation using playwright CLI
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "playwright",
                    "install",
                    "--dry-run",
                    "chromium",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # If exit code is 0 and no error in output, browsers are installed
            if result.returncode == 0 and "chromium" in result.stdout.lower():
                _PLAYWRIGHT_AVAILABLE = True
                logger.info("Playwright browsers verified: Chromium is installed")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Could not verify Playwright via CLI: {e}")

        # Fallback: Try to actually launch a browser (more reliable)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, timeout=5000)
                browser.close()
                _PLAYWRIGHT_AVAILABLE = True
                logger.info("Playwright browsers verified: Chromium launch successful")
                return True
        except Exception as e:
            error_msg = str(e).lower()
            # Check for common Playwright browser installation errors
            browser_missing_keywords = [
                "executable doesn't exist",
                "executable doesn't",
                "browser path",
                "chromium",
                "browser not installed",
                "no such file",
            ]
            if any(keyword in error_msg for keyword in browser_missing_keywords):
                logger.error(
                    "Playwright Chromium browser not installed or not found. "
                    "To install browsers, run:\n"
                    "  playwright install chromium\n"
                    "  OR\n"
                    "  playwright install\n\n"
                    "In Docker, ensure 'RUN playwright install chromium' is in your Dockerfile."
                )
            else:
                logger.warning(
                    f"Playwright browser verification failed: {e}\n"
                    "If this persists, try: playwright install chromium"
                )
            _PLAYWRIGHT_AVAILABLE = False
            return False

    except ImportError:
        logger.error(
            "Playwright is not installed. Install it with: pip install playwright"
        )
        _PLAYWRIGHT_AVAILABLE = False
        return False
    except Exception as e:
        logger.error(f"Unexpected error verifying Playwright: {e}")
        _PLAYWRIGHT_AVAILABLE = False
        return False


def _should_bail_early(domain: str) -> bool:
    info = _DOMAIN_FAILURE_CACHE.get(domain)
    if not info:
        return False
    # If repeated failures within this run, bail early on heavy operations
    return info.get("count", 0) >= 3


def _get_citations_for_pmid(pmid: str) -> int:
    """Fetch citation count for a PMID using NCBI efetch."""
    try:
        handle = Entrez.efetch(db="pubmed", id=pmid, report="xml")
        record = Entrez.read(handle)
        handle.close()

        # Extract citation count from the record
        if record and len(record) > 0:
            article = record[0]
            # Look for citation count in the record
            if "MedlineCitation" in article:
                medline = article["MedlineCitation"]
                if "NumberOfReferences" in medline:
                    return int(medline["NumberOfReferences"])
        return 0
    except Exception as e:
        logger.debug(f"Failed to get citations for PMID {pmid}: {e}")
        return 0


def _get_pmc_status(pmid: str) -> bool:
    """Check if PMID has a PMC ID (indicating PMC availability)."""
    try:
        base_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
        params = {
            "ids": pmid,
            "format": "json",
            "tool": "disease2gene",
            "email": config.ENTREZ_EMAIL,
        }
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        record = data.get("records", [{}])[0]
        return "pmcid" in record and record["pmcid"] is not None
    except Exception:
        return False


def _rank_pmids_by_priority(pmids: List[str]) -> Tuple[List[str], List[str]]:
    """Rank PMIDs: PMC first (by citations), then non-PMC (by citations)."""
    pmc_pmids = []
    non_pmc_pmids = []

    for pmid in pmids:
        if _get_pmc_status(pmid):
            pmc_pmids.append((pmid, _get_citations_for_pmid(pmid)))
        else:
            non_pmc_pmids.append((pmid, _get_citations_for_pmid(pmid)))

    # Sort by citations descending
    pmc_pmids.sort(key=lambda x: x[1], reverse=True)
    non_pmc_pmids.sort(key=lambda x: x[1], reverse=True)

    return [pmid for pmid, _ in pmc_pmids], [pmid for pmid, _ in non_pmc_pmids]


def run_fetching_prioritized(pmids: list, output_path: str, max_articles: int = 50):
    """
    Run fetching with PMC-first priority and citation ranking.
    """
    # Rank PMIDs by priority
    pmc_pmids, non_pmc_pmids = _rank_pmids_by_priority(pmids)

    logger.info(
        f"Found {len(pmc_pmids)} PMC articles and {len(non_pmc_pmids)} non-PMC articles"
    )

    # Combine lists with PMC first
    prioritized_pmids = pmc_pmids + non_pmc_pmids

    # Limit to max_articles if specified
    if max_articles:
        prioritized_pmids = prioritized_pmids[:max_articles]

    logger.info(
        f"Prioritizing {len(prioritized_pmids)} articles (PMC first, then by citations)"
    )

    # Run standard fetching on prioritized list
    return run_fetching(prioritized_pmids, output_path)


def _build_http_session() -> requests.Session:
    """Create a requests session with retries and sane headers."""
    session = requests.Session()
    retry = Retry(
        total=config.REQUEST_RETRIES,
        connect=config.REQUEST_RETRIES,
        read=config.REQUEST_RETRIES,
        backoff_factor=config.BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("HEAD", "GET", "OPTIONS"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


_SESSION = _build_http_session()


def _follow_meta_refresh(html: str, base_url: str) -> str:
    """If a meta refresh tag points to a URL, return that absolute URL; else base_url."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        meta = soup.find(
            "meta", attrs={"http-equiv": lambda v: v and v.lower() == "refresh"}
        )
        if not meta:
            return base_url
        content = meta.get("content", "")
        m = re.search(r"url=([^;]+)", content, flags=re.IGNORECASE)
        if not m:
            return base_url
        next_url = m.group(1).strip().strip("\"'")
        return urljoin(base_url, next_url)
    except Exception:
        return base_url


def _unpaywall_oa_url(doi_url: str) -> Optional[str]:
    """Use Unpaywall API to discover OA URL for a DOI if configured."""
    try:
        if not config.UNPAYWALL_EMAIL:
            return None
        parsed = urlparse(doi_url)
        if "doi.org" not in parsed.netloc.lower():
            return None
        doi = parsed.path.lstrip("/")
        if not doi:
            return None
        r = _SESSION.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": config.UNPAYWALL_EMAIL},
            timeout=config.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        best = data.get("best_oa_location") or {}
        return best.get("url")  # Removed pdf preference
    except Exception:
        return None


@dataclass
class ContentExtractionResult:
    """Result of content extraction with quality metrics."""

    pmid: str
    url: str
    content: str
    extraction_method: str
    content_length: int
    quality_score: float
    is_paywalled: bool
    content_type: str = "unknown"
    error_message: Optional[str] = None

    def is_good_quality(self, min_length: int = 1000, min_quality: float = 0.3) -> bool:
        """Check if extracted content meets quality thresholds."""
        return (
            self.content_length >= min_length
            and self.quality_score >= min_quality
            and not self.is_paywalled
            and self.error_message is None
            and self.content_type in ["full_article", "substantial_content"]
        )


def _get_url_from_pubmed_page(pmid: str) -> Union[str, None]:
    """
    As a fallback, scrapes the PubMed page directly for a link to the full text.
    Enhanced version with better link prioritization and multiple sources.
    """
    pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        response = _SESSION.get(
            pubmed_url, headers=headers, timeout=config.REQUEST_TIMEOUT
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Try multiple selectors for full-text links
        link_selectors = [
            "div.full-text-links-list a[href]",
            "div.fulltext-links a[href]",
            # High-quality sources
            'a[href*="pmc"]',  # PMC articles
            'a[href*="doi.org"]',  # DOI links
            'a[href*="sciencedirect"]',  # ScienceDirect
            'a[href*="linkinghub.elsevier"]',  # Elsevier linking hub
            'a[href*="wiley"]',  # Wiley
            'a[href*="onlinelibrary.wiley"]',  # Wiley online library
            'a[href*="springer"]',  # Springer
            'a[href*="link.springer"]',  # Springer linking
            'a[href*="nature"]',  # Nature
            'a[href*="plos"]',  # PLOS
            'a[href*="cell.com"]',  # Cell Press
            'a[href*="thelancet"]',  # Lancet
            'a[href*="nejm"]',  # NEJM
            'a[href*="jamanetwork"]',  # JAMA
            'a[href*="bmj"]',  # BMJ
            'a[href*="oup"]',  # Oxford UP
            'a[href*="tandfonline"]',  # Taylor & Francis
            'a[href*="aacrjournals"]',  # AACR
            'a[href*="ascopubs"]',  # ASCO
            'a[href*="lww"]',  # LWW
            'a[href*="karger"]',  # Karger
            'a[href*="frontiersin"]',  # Frontiers
            'a[href*="mdpi"]',  # MDPI
            'a[href*="hindawi"]',  # Hindawi
            # Generic full-text indicators
            'a[href*="full"]',  # Contains "full"
            'a[href*="article"]',  # Contains "article"
            'a[href*="retrieve"]',  # Retrieval links
        ]

        all_links: List[Any] = []
        for selector in link_selectors:
            links = soup.select(selector)
            if links:
                all_links.extend(links)

        # Prioritize links by quality and completeness
        if all_links:
            link_scores: List[Tuple[Any, str, float]] = []
            for link in all_links:
                href = link.get("href", "")
                score = _score_article_link(href, link.text.strip())
                link_scores.append((link, href, score))

            # Sort by score (highest first)
            link_scores.sort(key=lambda x: x[2], reverse=True)

            best_href = link_scores[0][1]
            logger.debug(
                f"Selected best link for PMID {pmid}: {best_href} (score: {link_scores[0][2]})"
            )
            return urljoin(pubmed_url, best_href)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to scrape PubMed page for {pmid}: {e}")
    return None


def _score_article_link(href: str, link_text: str) -> float:
    """Score article links by quality and completeness."""
    score = 0.0
    href_lower = href.lower()
    text_lower = link_text.lower()

    # High-quality sources get higher scores
    quality_keywords = {
        "pmc": 10,  # PMC is gold standard for full text
        "doi.org": 9,  # DOI links often lead to full text
        "sciencedirect": 8,  # ScienceDirect usually has full text
        "elsevier": 8,  # Elsevier journals
        "linkinghub.elsevier": 8,  # Elsevier linking hub
        "wiley": 8,  # Wiley journals
        "onlinelibrary.wiley": 8,  # Wiley online library
        "springer": 8,  # Springer journals
        "link.springer": 8,  # Springer linking
        "nature": 9,  # Nature journals
        "plos": 9,  # PLOS journals
        "cell.com": 8,  # Cell Press
        "thelancet": 8,  # Lancet journals
        "nejm": 9,  # NEJM
        "jamanetwork": 8,  # JAMA journals
        "bmj": 8,  # BMJ journals
        "oup": 8,  # Oxford University Press
        "tandfonline": 8,  # Taylor & Francis
        "aacrjournals": 8,  # AACR journals
        "ascopubs": 8,  # ASCO journals
        "lww": 8,  # Lippincott Williams & Wilkins
        "karger": 8,  # Karger journals
        "frontiersin": 8,  # Frontiers journals
        "mdpi": 8,  # MDPI journals
        "hindawi": 8,  # Hindawi journals
    }

    for keyword, weight in quality_keywords.items():
        if keyword in href_lower:
            score += weight
            break

    # Prefer links with "full text" in text
    if any(
        term in text_lower
        for term in ["full text", "full-text", "article", "full article"]
    ):
        score += 2

    # Prefer links that aren't just "abstract"
    if "abstract" not in text_lower:
        score += 1

    # Prefer specific article identifiers (PMCIDs, DOIs, etc.)
    if any(pattern in href_lower for pattern in ["pmc", "doi.org", "articles"]):
        score += 1

    # Penalize paywall indicators
    if any(
        term in href_lower
        for term in ["paywall", "subscription", "login", "premium", "access"]
    ):
        score -= 5

    # Prefer non-generic PMC links (specific article URLs over generic PMC)
    if "pmc" in href_lower and "articles" in href_lower:
        score += 2  # Specific PMC article URL

    return score


def _get_article_url_from_pmid(pmid: str) -> Union[str, None]:
    """
    Tries to find the full-text article URL for a given PMID.
    Enhanced version with multiple URL discovery methods.
    """
    urls = _get_multiple_article_urls(pmid)
    return urls[0] if urls else None


def _verify_pmc_id_matches_pmid(pmc_id: str, expected_pmid: str) -> bool:
    """
    Verify that a PMC ID corresponds to the expected PMID.
    Returns True if PMC ID matches PMID, False otherwise.
    """
    try:
        from Bio import Entrez
        import time
        
        # Rate limit: 3 requests per second
        time.sleep(0.34)
        
        pmc_num = pmc_id.replace('PMC', '')
        handle = Entrez.elink(dbfrom="pmc", db="pubmed", id=pmc_num)
        result = Entrez.read(handle)
        handle.close()
        
        if result and result[0].get('LinkSetDb'):
            actual_pmid = result[0]['LinkSetDb'][0]['Link'][0]['Id']
            matches = str(actual_pmid) == str(expected_pmid)
            if not matches:
                logger.warning(
                    f"PMC {pmc_id} does not match PMID {expected_pmid} "
                    f"(actual PMID: {actual_pmid})"
                )
            return matches
        return False
    except Exception as e:
        logger.debug(f"Could not verify PMC {pmc_id} for PMID {expected_pmid}: {e}")
        return False  # If we can't verify, don't trust it


def _extract_pmc_id_from_url(url: str) -> Optional[str]:
    """Extract PMC ID from a URL."""
    import re
    if not url:
        return None
    
    # Format 1: https://pmc.ncbi.nlm.nih.gov/articles/7474869/ (no /pmc/ in path)
    match = re.search(r'pmc\.ncbi\.nlm\.nih\.gov/articles/(\d+)', url)
    if match:
        return f"PMC{match.group(1)}"
    
    # Format 2: https://www.ncbi.nlm.nih.gov/pmc/articles/7474869/
    match = re.search(r'/pmc/articles/(\d+)', url)
    if match:
        return f"PMC{match.group(1)}"
    
    # Format 3: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7474869/
    match = re.search(r'/pmc/articles/(PMC\d+)', url)
    if match:
        return match.group(1)
    
    return None


def _get_multiple_article_urls(pmid: str) -> List[str]:
    """
    Try multiple methods to find article URLs for a PMID.
    Returns a list of potential URLs sorted by quality.
    Only includes PMC URLs that are verified to match the PMID.
    """
    urls = []
    verified_pmc_urls = []

    # Method 1: Official NCBI API (PMC/DOI conversion)
    base_url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    params = {
        "ids": pmid,
        "format": "json",
        "tool": "disease2gene",
        "email": config.ENTREZ_EMAIL,
    }
    try:
        response = requests.get(base_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        record = data.get("records", [{}])[0]
        if "pmcid" in record and record["pmcid"]:
            pmc_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{record['pmcid']}/"
            # Verify PMC ID matches PMID (should always match from NCBI API, but verify anyway)
            if _verify_pmc_id_matches_pmid(record["pmcid"], pmid):
                verified_pmc_urls.append(pmc_url)
            else:
                logger.warning(
                    f"NCBI API returned PMC {record['pmcid']} for PMID {pmid}, "
                    f"but verification failed - skipping"
                )
        if "doi" in record and record["doi"]:
            doi_url = f"https://doi.org/{record['doi']}"
            if doi_url not in urls:
                urls.append(doi_url)
    except requests.exceptions.RequestException as e:
        logger.debug(f"NCBI API failed for PMID {pmid}: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error in NCBI API for PMID {pmid}: {e}")

    # Method 2: PubMed page scraping (as fallback)
    pubmed_scraped_url = _get_url_from_pubmed_page(pmid)
    if pubmed_scraped_url and pubmed_scraped_url not in urls:
        # Only add if it's not the generic PMC URL
        if not (
            pubmed_scraped_url == "https://www.ncbi.nlm.nih.gov/pmc/"
            or pubmed_scraped_url.endswith("/pmc/")
        ):
            # If it's a PMC URL, verify it matches the PMID
            pmc_id = _extract_pmc_id_from_url(pubmed_scraped_url)
            if pmc_id:
                if _verify_pmc_id_matches_pmid(pmc_id, pmid):
                    verified_pmc_urls.append(pubmed_scraped_url)
                else:
                    logger.warning(
                        f"PubMed page scraping found PMC {pmc_id} for PMID {pmid}, "
                        f"but it doesn't match - skipping"
                    )
            else:
                # Not a PMC URL, add it (DOI or publisher URL)
                urls.append(pubmed_scraped_url)

    # Method 3: DOI-based URL construction (if we have DOI from other sources)
    try:
        # Try to get DOI from PubMed API first
        doi_response = _SESSION.get(
            f"https://api.crossref.org/works/{pmid}", timeout=10
        )
        if doi_response.status_code == 200:
            doi_data = doi_response.json()
            if "message" in doi_data and "DOI" in doi_data["message"]:
                doi = doi_data["message"]["DOI"]
                doi_url = f"https://doi.org/{doi}"
                if doi_url not in urls:
                    urls.append(doi_url)
    except Exception as e:
        logger.debug(f"DOI lookup failed for PMID {pmid}: {e}")

    # Method 4: Try to find DOI from PubMed abstract page
    try:
        pubmed_abstract_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        response = _SESSION.get(pubmed_abstract_url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            # Look for DOI in meta tags or text
            doi_meta = soup.find("meta", {"name": "citation_doi"}) or soup.find(
                "meta", {"property": "citation_doi"}
            )
            if doi_meta and doi_meta.get("content"):
                doi = doi_meta["content"]
                doi_url = f"https://doi.org/{doi}"
                if doi_url not in urls:
                    urls.append(doi_url)
    except Exception as e:
        logger.debug(f"DOI extraction from PubMed page failed for PMID {pmid}: {e}")

    # Filter out generic PMC URLs and duplicates, then sort by quality
    filtered_urls = []
    for url in urls:
        # Skip generic PMC URLs
        if url == "https://www.ncbi.nlm.nih.gov/pmc/" or url.endswith("/pmc/"):
            continue
        if url not in filtered_urls:
            filtered_urls.append(url)

    # Add verified PMC URLs first (these are already verified to match PMID)
    # Then add other URLs (DOI, publisher URLs)
    ordered = verified_pmc_urls.copy()
    
    # Score and sort other URLs (non-PMC)
    other_urls = []
    for url in filtered_urls:
        # Skip if already in verified_pmc_urls
        if url in verified_pmc_urls:
            continue
        # Skip if it's a PMC URL that wasn't verified
        if "ncbi.nlm.nih.gov/pmc" in url.lower() or "/pmc/articles/" in url.lower():
            logger.debug(f"Skipping unverified PMC URL: {url}")
            continue
        other_urls.append((url, _score_article_link(url, "")))

    # Sort other URLs by score
    other_urls.sort(key=lambda x: x[1], reverse=True)
    
    # Add other URLs after verified PMC URLs
    ordered.extend([url for url, score in other_urls])

    if verified_pmc_urls:
        logger.info(
            f"PMID {pmid}: Prioritizing {len(verified_pmc_urls)} verified PMC URL(s) before {len(other_urls)} other sources"
        )
    logger.debug(f"Found {len(ordered)} URLs for PMID {pmid} (verified PMC first): {ordered}")

    return ordered


def _extract_content_with_requests(url: str) -> Tuple[Optional[str], bool, int]:
    """
    Extract content using requests and Trafilatura (fastest method).
    Returns (content, is_paywalled, status_code)
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        response = _SESSION.get(
            url, headers=headers, timeout=config.REQUEST_TIMEOUT, allow_redirects=True
        )
        response.raise_for_status()

        # Follow meta-refresh redirects
        meta_next = _follow_meta_refresh(response.text, response.url)
        if meta_next and meta_next != response.url:
            try:
                r2 = _SESSION.get(
                    meta_next, timeout=config.REQUEST_TIMEOUT, allow_redirects=True
                )
                if r2.status_code == 200 and len(r2.text) > len(response.text):
                    response = r2
            except Exception:
                pass

        # Use Trafilatura for content extraction
        extracted = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=True,  # Include tables for better content
            deduplicate=True,
            favor_precision=True,
            include_links=False,
        )

        if extracted:
            cleaned_content, content_type = _clean_and_validate_content(
                extracted, response.url
            )
            is_paywalled = _detect_paywall(
                extracted, response.url, response.status_code
            )
            return cleaned_content, is_paywalled, response.status_code

        # Try Unpaywall OA URL if this is a DOI
        if "doi.org" in response.url.lower():
            oa_url = _unpaywall_oa_url(response.url)
            if oa_url:
                try:
                    orr = _SESSION.get(
                        oa_url, timeout=config.REQUEST_TIMEOUT, allow_redirects=True
                    )
                    if orr.status_code == 200:
                        extracted2 = trafilatura.extract(
                            orr.text,
                            include_comments=False,
                            include_tables=True,
                            deduplicate=True,
                            favor_precision=True,
                        )
                        if extracted2 and len(extracted2.strip()) > 200:
                            cleaned_content, content_type = _clean_and_validate_content(
                                extracted2, orr.url
                            )
                            is_paywalled = _detect_paywall(
                                extracted2, orr.url, orr.status_code
                            )
                            return cleaned_content, is_paywalled, orr.status_code
                except Exception:
                    pass

        return None, False, 200

    except requests.exceptions.RequestException as e:
        logger.debug(f"Requests extraction failed for {url}: {e}")
        return None, False, 0
    except Exception as e:
        logger.debug(f"Unexpected error in requests extraction for {url}: {e}")
        return None, False, 0


def _fetch_with_playwright(url: str) -> Tuple[Optional[str], bool, int]:
    """
    Uses Playwright to render the page and extract content (more reliable for JS-heavy sites).
    Returns (content, is_paywalled, status_code)
    """
    if not url:
        return None, False, 0

    # Verify Playwright is available before attempting to use it
    if not _verify_playwright_installation():
        logger.warning(
            "Playwright browser not available. Skipping Playwright extraction. "
            "Install browsers with: playwright install chromium"
        )
        return None, False, 0

    try:
        browser = None
        context = None
        page = None
        with sync_playwright() as p:
            # Use headless mode for better performance
            browser = p.chromium.launch(headless=True)
            try:
                # Set up context with better mobile emulation to avoid some paywalls
                context = browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                )

                page = context.new_page()

                # Per-domain timeout and navigate
                domain = _get_domain_from_url(url)
                timeout_ms = _domain_timeout_ms(domain)
                if _should_bail_early(domain):
                    return None, False, 0
                # Navigate to the page and get response
                response = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                status_code = response.status if response else 200

                # Try to accept cookie banners and popups
                _handle_cookie_banners(page)

                # Wait for content to load and trigger lazy-loaded sections
                # Add timeout to prevent indefinite hangs
                try:
                    page.wait_for_load_state(
                        "networkidle", timeout=30000
                    )  # 30s timeout
                except Exception:
                    pass  # Continue even if networkidle times out

                for _ in range(3):
                    try:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass
                    page.wait_for_timeout(1500)
                    try:
                        page.wait_for_load_state(
                            "networkidle", timeout=30000
                        )  # 30s timeout
                    except Exception:
                        break  # If networkidle fails, stop trying

                # Check for paywall indicators, but still attempt extraction
                page_content = page.content()
                is_paywalled = _detect_paywall(page_content, url, status_code)

                # Domain-specific routines
                try:
                    if "ascopubs.org" in domain:
                        # Try HTML view
                        el = page.locator(
                            'a:has-text("View HTML"), a:has-text("Full Text")'
                        ).first
                        if el and el.count() > 0 and el.is_visible():
                            el.click(timeout=3000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=30000)
                            except Exception:
                                pass
                            page.wait_for_timeout(1500)
                    if "tandfonline.com" in domain:
                        # Expand full text panel
                        el = page.locator('button:has-text("Full text")').first
                        if el and el.count() > 0 and el.is_visible():
                            el.click(timeout=3000)
                            page.wait_for_timeout(1500)
                    if "annualreviews.org" in domain:
                        # Prefer crawler pdf url if available
                        try:
                            href = page.url
                            if (
                                "crawler=true" not in href
                                and "annualreviews.org" in href
                            ):
                                # Attempt appending crawler param
                                page.goto(
                                    href
                                    + (("&" if "?" in href else "?") + "crawler=true"),
                                    timeout=timeout_ms,
                                    wait_until="networkidle",
                                )
                                page.wait_for_timeout(1000)
                        except Exception:
                            pass
                except Exception:
                    pass

                # Try common CTAs to reveal full text
                try:
                    cta_selectors = [
                        'a:has-text("Full Text")',
                        'a:has-text("Read full text")',
                        'a:has-text("View HTML")',
                        'a:has-text("Article")',
                        'button:has-text("Full Text")',
                        'a[title*="Full text"]',
                    ]
                    for sel in cta_selectors:
                        el = page.locator(sel).first
                        if el and el.count() > 0 and el.is_visible():
                            try:
                                el.click(timeout=3000)
                                try:
                                    page.wait_for_load_state(
                                        "networkidle", timeout=30000
                                    )
                                except Exception:
                                    pass
                                page.wait_for_timeout(1500)
                                break
                            except Exception:
                                continue
                except Exception:
                    pass

                # Enhanced content extraction with multiple strategies
                content = _extract_comprehensive_content(page, url)

                # Extract iframe URLs before closing browser
                iframe_srcs = []
                try:
                    iframe_srcs = (
                        page.evaluate(
                            'Array.from(document.querySelectorAll("iframe")).map(f => f.src)'
                        )
                        or []
                    )
                except Exception:
                    pass

                # Close browser before processing iframes
                browser.close()
                browser = None

                if content and len(content.strip()) > 100:
                    cleaned_content, content_type = _clean_and_validate_content(
                        content, url
                    )
                    # Even if paywall indicators exist, return extracted content
                    return cleaned_content, False, status_code

                # Try iframes for embedded full-text content
                if iframe_srcs:
                    try:
                        for src in iframe_srcs:
                            if not src:
                                continue
                            try:
                                pr = _SESSION.get(
                                    src,
                                    timeout=config.REQUEST_TIMEOUT,
                                    allow_redirects=True,
                                )
                                ctype = pr.headers.get("Content-Type", "").lower()
                                # Skip PDF iframes - PDF extraction not ready
                                if "application/pdf" in ctype or src.lower().endswith(
                                    ".pdf"
                                ):
                                    continue
                                else:
                                    # Try extracting HTML from iframe URL
                                    extracted2 = trafilatura.extract(
                                        pr.text,
                                        include_comments=False,
                                        include_tables=True,
                                        deduplicate=True,
                                        favor_precision=True,
                                    )
                                    if extracted2 and len(extracted2.strip()) > 200:
                                        cleaned_content, content_type = (
                                            _clean_and_validate_content(extracted2, src)
                                        )
                                        return cleaned_content, False, pr.status_code
                            except Exception:
                                continue
                    except Exception:
                        pass
            finally:
                # Ensure browser is always closed, even on exceptions
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass

    except Exception as e:
        logger.debug(f"Playwright failed for URL {url}: {e}")
        # Browser cleanup handled by finally block above

    return None, False, 0


def _handle_cookie_banners(page) -> None:
    """Handle cookie consent banners and popups."""
    try:
        # Common cookie banner selectors
        cookie_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Accept all")',
            'button:has-text("Accept cookies")',
            'button:has-text("I agree")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            '[data-testid="cookie-accept"]',
            "[data-accept-cookies]",
        ]

        for selector in cookie_selectors:
            try:
                elements = page.locator(selector).all()
                if elements:
                    elements[0].click(timeout=2000)
                    page.wait_for_timeout(1000)
                    break
            except:
                continue

        # Also try to dismiss any overlay modals
        try:
            overlay = page.locator('[role="dialog"], .modal, .overlay, .popup').first
            if overlay.is_visible(timeout=2000):
                close_button = overlay.locator(
                    'button[aria-label*="Close"], button[class*="close"], [data-dismiss]'
                ).first
                if close_button.count() > 0:
                    close_button.click(timeout=2000)
        except:
            pass

    except Exception as e:
        logger.debug(f"Cookie banner handling failed: {e}")


def _extract_comprehensive_content(page, url: str) -> Optional[str]:
    """Extract content using multiple strategies and selectors."""
    domain = urlparse(url).netloc.lower()

    # Publisher-specific content selectors (enhanced)
    publisher_selectors = {
        # PMC/NIH
        "ncbi.nlm.nih.gov": [
            "div.article-content",
            "article",
            "main",
            "div#article-body",
        ],
        # ScienceDirect
        "sciencedirect.com": ["div#body", "div.article-body", "article", "main"],
        # Wiley
        "onlinelibrary.wiley.com": [
            "div.article-body",
            "article",
            "main",
            "div.content",
        ],
        # Springer
        "link.springer.com": ["main#main-content", "article", "div.content"],
        # Nature
        "nature.com": [
            'article[data-test="article.main"]',
            "div.article-body",
            "article",
            "main",
        ],
        # PLOS
        "journals.plos.org": ["div.article-body", "article", "main"],
        # Cell Press
        "cell.com": ["div.article-content", "article", "main"],
        # Generic academic publishers
        "tandfonline.com": ["div.hlFld-Fulltext", "article", "main"],
        "aacrjournals.org": ["div.article__body", "article", "main"],
        "journals.lww.com": ["div#Full-Text-Content", "article", "main"],
        # ASCO Publications
        "ascopubs.org": ["div.article__body", "article", "main"],
        # ARVO / IOVS
        "iovs.arvojournals.org": ["div.article-full-text", "article", "main"],
        # ACS Publications
        "pubs.acs.org": ["div.article_content-left", "article", "main"],
    }

    # Get appropriate selectors for this domain
    content_selectors: List[str] = []
    for domain_pattern, selectors in publisher_selectors.items():
        if domain_pattern in domain:
            content_selectors = selectors
            break

    # Fallback to generic selectors if no specific ones found
    if not content_selectors:
        content_selectors = [
            'article[role="main"]',
            'div[role="main"]',
            "main",
            "article",
            "div.article-body",
            "div.content",
            "div#body",
        ]

    # Try each selector
    for selector in content_selectors:
        try:
            elements = page.locator(selector).all()
            if elements:
                # Get the largest content block
                content_blocks: List[Tuple[int, str]] = []
                for element in elements:
                    html_content = element.inner_html()
                    if (
                        html_content and len(html_content.strip()) > 500
                    ):  # Minimum viable content
                        content_blocks.append((len(html_content), html_content))

                if content_blocks:
                    # Sort by size and take the largest
                    content_blocks.sort(key=lambda x: x[0], reverse=True)
                    largest_content = content_blocks[0][1]

                    # Extract clean text
                    extracted = trafilatura.extract(
                        largest_content,
                        include_comments=False,
                        include_tables=True,
                        deduplicate=True,
                        favor_precision=True,
                    )

                    if extracted and len(extracted.strip()) > 200:
                        return extracted

        except Exception as e:
            logger.debug(f"Selector {selector} failed for {url}: {e}")
            continue

    # If all selectors failed, try the entire page content as fallback
    try:
        full_html = page.content()
        extracted = trafilatura.extract(
            full_html,
            include_comments=False,
            include_tables=True,
            deduplicate=True,
            favor_precision=True,
        )

        if extracted and len(extracted.strip()) > 200:
            return extracted

    except Exception as e:
        logger.debug(f"Full page extraction failed for {url}: {e}")

    return None


def _detect_paywall(html_content: str, url: str, status_code: int = 200) -> bool:
    """Detect if a page is behind a paywall or access control."""
    html_lower = html_content.lower()
    url_lower = url.lower()

    # Never mark NIH/PMC pages as paywalled
    if any(host in url_lower for host in ["ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov"]):
        return False

    # Check HTTP status codes that indicate access issues
    if status_code in [401, 403, 407, 451]:
        return True

    # Check URL patterns that strongly indicate paywalls (quick check)
    paywall_domains = [
        "linkinghub.elsevier",
        "retrieve/pii/",
        "sciencedirect.com",
        "tandfonline.com",
        "informahealthcare.com",
        "wiley.com",
        "springer.com",
        "nature.com",
        "oup.com",
        "cambridge.org",
        "karger.com",
        "lww.com",
        "nejm.org",
        "thelancet.com",
        "jamanetwork.com",
        "ascopubs.org",
        "aacrjournals.org",
    ]

    for domain in paywall_domains:
        if domain in url_lower:
            # For known paywall domains, only flag if content is very minimal
            if len(html_content.strip()) < 2000:
                return True
            # For longer content, only flag if it has strong paywall indicators
            strong_paywall_terms = [
                "subscription required",
                "purchase access",
                "login to view",
                "access denied",
                "requires authentication",
            ]
            if any(term in html_lower for term in strong_paywall_terms):
                return True

    # Common paywall indicators
    paywall_indicators = [
        "paywall",
        "subscription required",
        "purchase access",
        "login to view",
        "register to read",
        "premium content",
        "subscriber only",
        "access denied",
        "forbidden",
        "unauthorized",
        "requires authentication",
        "please log in",
        "sign up to continue",
        "upgrade to premium",
        "become a subscriber",
        "pay per view",
        "article preview",
        "abstract only",
        "redirecting",
        "purchase article",
        "buy article",
        "institutional access",
        "remote access",
        "access provided by",
        "this content is not available",
        "purchase this article",
        "buy this article",
        "get access",
        "view full article",
        "full text access",
        "subscriber content",
        "member content",
    ]

    # Check for paywall text
    for indicator in paywall_indicators:
        if indicator in html_lower:
            # Special handling for "read more" / "continue reading"
            if indicator in ["read more", "continue reading"]:
                # Only treat as paywall if accompanied by access/purchase terms AND short content
                context_terms = [
                    "subscription",
                    "login",
                    "purchase",
                    "access",
                    "premium",
                    "paywall",
                ]
                if (
                    any(term in html_lower for term in context_terms)
                    and len(html_content.strip()) < 2000
                ):
                    return True
            else:
                return True

    # Check for very short content that might indicate access control
    # Only flag as paywall if content is very short AND has paywall indicators
    if len(html_content.strip()) < 3000:
        # Very short pages are likely access control or redirect pages
        paywall_terms = [
            "access",
            "login",
            "subscription",
            "purchase",
            "register",
            "sign in",
            "authenticate",
        ]
        if any(term in html_lower for term in paywall_terms):
            # Additional check: look for redirect patterns or minimal content
            if "redirect" in html_lower or len(html_content.strip()) < 1000:
                return True

    # Check for specific paywall patterns in content
    if len(html_content.strip()) < 500:
        # Extremely short content likely indicates access control
        if any(term in html_lower for term in ["access", "login", "subscription"]):
            return True

    # Check for JavaScript redirects or meta refresh to paywall pages
    if "window.location" in html_lower or 'meta http-equiv="refresh"' in html_lower:
        if any(term in html_lower for term in ["login", "subscription", "purchase"]):
            return True

    # Check for Elsevier/ScienceDirect specific redirect patterns
    if "sciencedirect.com" in url_lower or "linkinghub.elsevier" in url_lower:
        if "redirecting" in html_lower or len(html_content.strip()) < 1000:
            return True

    # Check for Taylor & Francis specific patterns
    if "tandfonline.com" in url_lower:
        if len(html_content.strip()) < 1500 or "informahealthcare" in html_lower:
            return True

    return False


def _clean_and_validate_content(content: str, url: str) -> Tuple[str, str]:
    """
    Clean and validate extracted content.

    Returns:
        Tuple of (cleaned_content, content_type)
        content_type: 'full_article', 'abstract_only', 'access_page', or 'empty'
    """
    if not content:
        return "", "empty"

    # Basic cleaning
    cleaned = re.sub(r"\s+", " ", content)  # Normalize whitespace
    cleaned = re.sub(r"[^\x00-\x7F]+", " ", cleaned)  # Remove non-ASCII characters
    cleaned = re.sub(r"\s+", " ", cleaned).strip()  # Final cleanup

    # Determine content type based on URL and content characteristics
    url_lower = url.lower()
    content_lower = cleaned.lower()

    # Check if this is an access control/redirect page
    if any(domain in url_lower for domain in ["linkinghub.elsevier", "retrieve/pii/"]):
        # This is an Elsevier access page
        if "redirecting" in content_lower or len(cleaned) < 50:
            return "", "access_page"
        else:
            # Might have some content (abstract, etc.)
            if len(cleaned) > 500:
                return cleaned, "abstract_content"
            else:
                return cleaned, "access_page"

    # Check for academic content indicators
    academic_indicators = [
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "figure",
        "table",
        "references",
        "acknowledgment",
    ]

    academic_score = sum(
        1 for indicator in academic_indicators if indicator in content_lower
    )

    # Validate content quality
    if len(cleaned) < 100:
        return "", "empty"

    # Classify content type
    if len(cleaned) > 5000 and academic_score >= 3:
        content_type = "full_article"
    elif len(cleaned) > 1000 and academic_score >= 2:
        content_type = "substantial_content"
    elif len(cleaned) > 500 and academic_score >= 1:
        content_type = "abstract_content"
    elif any(term in url_lower for term in ["pmc", "articles"]):
        content_type = "full_article"  # PMC articles should be full
    else:
        content_type = "minimal_content"

    # Check for obvious non-content (just navigation, ads, etc.)
    non_content_indicators = [
        "advertisement",
        "sponsored content",
        "related articles",
        "recommended reading",
        "most popular",
        "trending now",
    ]

    content_lower = cleaned.lower()
    non_content_count = sum(
        1 for indicator in non_content_indicators if indicator in content_lower
    )

    if non_content_count > 2:  # If multiple non-content indicators
        logger.warning(
            f"Content may be low quality for {url}: too many non-content indicators"
        )
        content_type = "low_quality"

    return cleaned, content_type


def _extract_content_robust(url: str) -> ContentExtractionResult:
    """
    Robust content extraction with multiple fallback strategies.
    Returns a ContentExtractionResult with quality metrics.
    """
    pmid = "unknown"  # We'll set this later

    # Strategy 1: Fast requests-based extraction
    content, is_paywalled, status_code = _extract_content_with_requests(url)

    if content and not is_paywalled:
        quality_score = _assess_content_quality(content, url)
        # For requests method, we need to determine content type
        _, content_type = _clean_and_validate_content(content, url)
        return ContentExtractionResult(
            pmid=pmid,
            url=url,
            content=content,
            extraction_method="requests_trafilatura",
            content_length=len(content),
            quality_score=quality_score,
            is_paywalled=False,
            content_type=content_type,
        )

    # Strategy 2: Playwright-based extraction (more thorough)
    if not is_paywalled:  # Only try playwright if not obviously paywalled
        content, is_paywalled, status_code = _fetch_with_playwright(url)

        if content and not is_paywalled:
            quality_score = _assess_content_quality(content, url)
            # For playwright method, content type should be determined in _clean_and_validate_content
            _, content_type = _clean_and_validate_content(content, url)
            return ContentExtractionResult(
                pmid=pmid,
                url=url,
                content=content,
                extraction_method="playwright_trafilatura",
                content_length=len(content),
                quality_score=quality_score,
                is_paywalled=False,
                content_type=content_type,
            )

    # If we reach here, either paywalled or extraction failed
    return ContentExtractionResult(
        pmid=pmid,
        url=url,
        content="",
        extraction_method="failed",
        content_length=0,
        quality_score=0.0,
        is_paywalled=is_paywalled,
        error_message="Content extraction failed or paywalled",
    )


def _assess_content_quality(content: str, url: str) -> float:
    """Assess the quality of extracted content."""
    if not content or len(content) < 100:
        return 0.0

    score = 0.0

    # Length factor (longer content is generally better)
    content_len = len(content)
    if content_len > 5000:
        score += 0.3
    elif content_len > 2000:
        score += 0.2
    elif content_len > 1000:
        score += 0.1

    # Word count factor
    word_count = len(content.split())
    if word_count > 1000:
        score += 0.2
    elif word_count > 500:
        score += 0.1

    # Content diversity (sentences vs. repetitive text)
    sentences = len(re.split(r"[.!?]+", content))
    if sentences > 20:
        score += 0.2
    elif sentences > 10:
        score += 0.1

    # Check for academic content indicators
    academic_indicators = [
        "abstract",
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
        "figure",
        "table",
        "references",
        "acknowledgment",
    ]

    academic_score = sum(
        1 for indicator in academic_indicators if indicator in content.lower()
    )
    score += min(academic_score * 0.05, 0.2)  # Cap at 0.2

    # Penalize obvious non-content
    if any(
        indicator in content.lower()
        for indicator in ["advertisement", "sponsored", "login required"]
    ):
        score -= 0.3

    return min(max(score, 0.0), 1.0)  # Clamp between 0 and 1


def _process_single_pmid(pmid: str) -> Union[ContentExtractionResult, None]:
    """
    Orchestrates the fetching and extraction for a single PMID with comprehensive error handling.
    """
    # Get all possible URLs for this PMID
    article_urls = _get_multiple_article_urls(pmid)

    if not article_urls:
        logger.warning(f"No URLs found for PMID {pmid}")
        return ContentExtractionResult(
            pmid=pmid,
            url="",
            content="",
            extraction_method="no_url_found",
            content_length=0,
            quality_score=0.0,
            is_paywalled=False,
            error_message="No article URLs found",
        )

    # Try each URL; attempt some in parallel batches with short timeouts to reduce total latency
    for i, article_url in enumerate(article_urls):
        logger.info(
            f"Trying URL {i+1}/{len(article_urls)} for PMID {pmid}: {article_url}"
        )

        try:
            # Early bail per domain
            if _should_bail_early(_get_domain_from_url(article_url)):
                logger.debug(
                    f"Bailing early for domain due to repeated failures: {article_url}"
                )
                continue

            result = _extract_content_robust(article_url)
            result.pmid = pmid  # Set the actual PMID

            # Log extraction results
            if result.content and not result.is_paywalled:
                logger.info(
                    f"Successfully extracted content for PMID {pmid}: {result.content_length} chars, {result.quality_score:.2f} quality, method: {result.extraction_method}"
                )
            elif result.is_paywalled:
                logger.warning(f"Paywall detected for PMID {pmid} at {article_url}")
                _note_domain_failure(_get_domain_from_url(article_url), "paywall")
                continue  # Try next URL
            else:
                logger.debug(
                    f"Extraction failed for PMID {pmid} at {article_url}: {result.error_message}"
                )
                _note_domain_failure(
                    _get_domain_from_url(article_url), result.error_message or "unknown"
                )
                continue  # Try next URL

            # If we got good content, return it
            if result.is_good_quality():
                logger.info(f"High-quality content extracted for PMID {pmid}")
                return result
            else:
                logger.debug(
                    f"Low-quality content for PMID {pmid}: {result.content_length} chars, {result.quality_score:.2f} quality, type: {result.content_type}"
                )

        except Exception as e:
            logger.error(
                f"Unexpected error processing PMID {pmid} at {article_url}: {e}"
            )
            continue

    # If we tried all URLs and none worked
    logger.warning(
        f"Could not retrieve quality full text for PMID {pmid} after trying {len(article_urls)} URLs"
    )
    return ContentExtractionResult(
        pmid=pmid,
        url=article_urls[0] if article_urls else "",
        content="",
        extraction_method="all_methods_failed",
        content_length=0,
        quality_score=0.0,
        is_paywalled=False,
        error_message=f"Tried {len(article_urls)} URLs, all failed or paywalled",
    )


def run_fetching(pmids: list, output_path: str):
    """
    Main function to run the full-text fetching process on a list of PMIDs with enhanced extraction.
    """
    # Verify Playwright installation at startup to fail fast if not available
    _verify_playwright_installation()
    content_dict = {}
    success_count = 0
    paywall_count = 0
    failure_count = 0

    max_workers = getattr(config, "FETCH_MAX_WORKERS", 6)
    thread_timeout = getattr(config, "FETCH_THREAD_TIMEOUT", 300)
    logger.info(f"Starting parallel extraction with up to {max_workers} workers")
    logger.info(f"Thread timeout: {thread_timeout}s per PMID")

    # Track parallelization performance
    from .progress_tracker import get_tracker

    tracker = get_tracker()
    extraction_timer = tracker.start_step(
        "Full-Text Extraction",
        f"Processing {len(pmids)} PMIDs with {max_workers} workers",
    )

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_pmid = {
            executor.submit(_process_single_pmid, pmid): pmid for pmid in pmids
        }

        # Use wait() with timeout to prevent indefinite blocking
        # Process futures as they complete, but don't wait forever
        all_futures = set(future_to_pmid.keys())
        processed_futures = set()
        max_total_timeout = thread_timeout * len(pmids)  # Maximum total time
        start_time = time.time()

        with tqdm(total=len(pmids), desc="Extracting Full-Text Content") as pbar:
            # Track when each future started
            future_start_times = {future: time.time() for future in all_futures}

            while len(processed_futures) < len(pmids):
                # Check if we've exceeded maximum timeout
                elapsed = time.time() - start_time
                if elapsed > max_total_timeout:
                    logger.warning(
                        f"Exceeded maximum total timeout ({max_total_timeout}s). "
                        f"Processing {len(processed_futures)}/{len(pmids)} completed, "
                        f"marking remaining as failed."
                    )
                    break

                # Check for stuck futures (running longer than thread_timeout)
                current_time = time.time()
                stuck_futures = []
                for future in all_futures - processed_futures:
                    future_runtime = current_time - future_start_times.get(
                        future, current_time
                    )
                    if future_runtime > thread_timeout:
                        stuck_futures.append(future)

                # Mark stuck futures as failed
                if stuck_futures:
                    logger.warning(
                        f"Found {len(stuck_futures)} stuck futures, marking as failed"
                    )
                    for future in stuck_futures:
                        if future not in processed_futures:
                            processed_futures.add(future)
                            pmid = future_to_pmid[future]
                            pbar.update(1)
                            logger.error(
                                f"PMID {pmid} exceeded timeout ({thread_timeout}s) - marking as failed"
                            )
                            failure_count += 1
                    # Break immediately if we've processed all futures
                    if len(processed_futures) >= len(pmids):
                        logger.info(
                            f"All {len(pmids)} PMIDs processed (stuck futures marked as failed)"
                        )
                        break

                # If we've already processed all futures, break immediately
                if len(processed_futures) >= len(pmids):
                    break

                # Wait for at least one future to complete, with timeout
                done, not_done = concurrent.futures.wait(
                    all_futures - processed_futures,
                    timeout=10,  # Reduced timeout to check more frequently
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                # Process all completed futures
                for future in done:
                    if future in processed_futures:
                        continue
                    processed_futures.add(future)
                    pmid = future_to_pmid[future]
                    pbar.update(1)

                    try:
                        # Get result with short timeout (should be ready if done)
                        try:
                            result = future.result(timeout=1)
                        except concurrent.futures.TimeoutError:
                            logger.warning(
                                f"PMID {pmid} future not ready despite being done"
                            )
                            failure_count += 1
                            continue

                        if result:
                            content_dict[result.pmid] = {
                                "pmid": result.pmid,
                                "url": result.url,
                                "content": result.content,
                                "extraction_method": result.extraction_method,
                                "content_length": result.content_length,
                                "quality_score": result.quality_score,
                                "is_paywalled": result.is_paywalled,
                                "content_type": result.content_type,
                                "error_message": result.error_message,
                                "type": "text" if result.content else "failed",
                            }

                            if result.is_paywalled:
                                paywall_count += 1
                            elif result.content_length > 0:
                                success_count += 1
                            else:
                                failure_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"Unexpected error processing PMID {pmid}: {e}")
                        failure_count += 1

                # If no futures completed and we've waited, check for timeouts
                if not done and len(processed_futures) < len(pmids):
                    # Check if any futures have been running too long
                    for future in not_done:
                        if future in processed_futures:
                            continue
                        pmid = future_to_pmid[future]
                        # Try to get result with timeout to detect stuck threads
                        try:
                            result = future.result(timeout=1)
                            # If we get here, the future is actually done
                            processed_futures.add(future)
                            pbar.update(1)
                            if result:
                                content_dict[result.pmid] = {
                                    "pmid": result.pmid,
                                    "url": result.url,
                                    "content": result.content,
                                    "extraction_method": result.extraction_method,
                                    "content_length": result.content_length,
                                    "quality_score": result.quality_score,
                                    "is_paywalled": result.is_paywalled,
                                    "content_type": result.content_type,
                                    "error_message": result.error_message,
                                    "type": "text" if result.content else "failed",
                                }
                                if result.is_paywalled:
                                    paywall_count += 1
                                elif result.content_length > 0:
                                    success_count += 1
                                else:
                                    failure_count += 1
                            else:
                                failure_count += 1
                        except concurrent.futures.TimeoutError:
                            # Future is still running - check if it's been too long
                            # We can't easily check runtime, so we'll let it continue
                            # The timeout on wait() will eventually catch it
                            pass
                        except Exception as e:
                            logger.error(f"Error checking future for PMID {pmid}: {e}")
                            processed_futures.add(future)
                            pbar.update(1)
                            failure_count += 1

        # Handle any remaining unprocessed futures as timeouts
        remaining = all_futures - processed_futures
        if remaining:
            logger.warning(
                f"{len(remaining)} threads did not complete - marking as failed"
            )
            for future in remaining:
                pmid = future_to_pmid[future]
                logger.error(f"PMID {pmid} did not complete within timeout")
                failure_count += 1

    finally:
        # Ensure the executor does not block shutdown on lingering threads
        try:
            executor.shutdown(wait=False)
            logger.info(
                "ThreadPoolExecutor shutdown initiated (not waiting for stuck threads)"
            )
        except Exception as e:
            logger.warning(f"Error shutting down executor: {e}")

    # Stop timing and track parallelization stats
    logger.info("Starting extraction timer stop and parallelization tracking")
    extraction_timer.stop()
    elapsed_time = extraction_timer.elapsed or 0.0
    tracker.track_parallelization(
        step_name="Full-Text Extraction",
        total_items=len(pmids),
        num_workers=max_workers,
        elapsed_time=elapsed_time,
        successful=success_count,
        failed=failure_count + paywall_count,
    )

    # Log summary statistics
    total_processed = success_count + paywall_count + failure_count
    if total_processed > 0:
        logger.info("Full-text extraction summary:")
        logger.info(
            f"  Successfully extracted: {success_count}/{total_processed} ({success_count/total_processed*100:.1f}%)"
        )
        logger.info(
            f"  Paywall blocked: {paywall_count}/{total_processed} ({paywall_count/total_processed*100:.1f}%)"
        )
        logger.info(
            f"  Extraction failed: {failure_count}/{total_processed} ({failure_count/total_processed*100:.1f}%)"
        )

    try:
        with gzip.open(output_path, "wb") as f:
            pickle.dump(content_dict, f)
        logger.info(
            f"Saved extracted content for {len(content_dict)} PMIDs to {output_path}"
        )
    except IOError as e:
        logger.error(f"Failed to save content dictionary: {e}")
        return None

    return content_dict
