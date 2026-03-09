# modules/config.py

import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# --- Paths ---
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
OUTPUT_DIR = os.path.join(DATA_DIR, 'output')

# --- API Configs ---
# Load from environment, can be overridden by entrypoint script
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENTREZ_API_KEY = os.getenv("ENTREZ_API_KEY")
# --- PubMed Search ---
# Sort options: 'relevance', 'pub+date', etc.
PUBMED_SORT = os.getenv("PUBMED_SORT", "relevance")
# How many of the most relevant PubMed articles to fetch before filtering
PUBMED_RELEVANT_COUNT = int(os.getenv("PUBMED_RELEVANT_COUNT", "200"))

# Open-access full text filter: restricts PubMed results to papers with free full text
ENABLE_OA_FILTER = os.getenv("ENABLE_OA_FILTER", "true").lower() == "true"

# FIX #1: Publication Type Filtering (Est. 40% waste reduction)
ENABLE_PUBLICATION_TYPE_FILTER = os.getenv("ENABLE_PUBLICATION_TYPE_FILTER", "true").lower() == "true"
EXCLUDED_PUBLICATION_TYPES = [
    'Review', 'Meta-Analysis', 'Systematic Review',
    'Editorial', 'Comment', 'Letter', 'News',
    'Practice Guideline', 'Guideline', 'Clinical Trial Protocol',
    'Consensus Development Conference', 'Consensus Development Conference, NIH'
]

# FIX #2: Abstract Pre-Screening (Est. 30% additional reduction)
ENABLE_ABSTRACT_SCREENING = os.getenv("ENABLE_ABSTRACT_SCREENING", "true").lower() == "true"
ABSTRACT_SCREENING_THRESHOLD = int(os.getenv("ABSTRACT_SCREENING_THRESHOLD", "5"))  # Minimum score to proceed

# FIX #5 (Revised): Two-Stage Gemini Pipeline (Est. 50% additional reduction)
# Use Flash on abstracts for gene discovery, then Pro on full text for extraction
ENABLE_ABSTRACT_GENE_DISCOVERY = os.getenv("ENABLE_ABSTRACT_GENE_DISCOVERY", "true").lower() == "true"

# Grounding check: drop candidate genes not found in the fetched paper text before Stage 3.
# Prevents hallucinated genes (recalled from training knowledge, not from the text) from
# generating empty rows in the final CSV. Set to "false" to disable, e.g. when debugging.
ENABLE_GROUNDING_CHECK = os.getenv("ENABLE_GROUNDING_CHECK", "true").lower() == "true"


BATCH_SIZE = 100
RETRIES = 1

# --- HTTP client/networking ---
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
REQUEST_RETRIES = int(os.getenv("REQUEST_RETRIES", "3"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "0.5"))

# --- Unpaywall (for OA discovery) ---
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL")

# --- OA full-text source strategy ---
ENABLE_EUROPE_PMC_FALLBACK = os.getenv("ENABLE_EUROPE_PMC_FALLBACK", "true").lower() == "true"
ENABLE_PLAYWRIGHT_FALLBACK = os.getenv("ENABLE_PLAYWRIGHT_FALLBACK", "false").lower() == "true"

# Supplementary extraction (tables/data files linked by article)
ENABLE_SUPPLEMENTARY_EXTRACTION = os.getenv("ENABLE_SUPPLEMENTARY_EXTRACTION", "true").lower() == "true"
SUPPLEMENTARY_MAX_FILES = int(os.getenv("SUPPLEMENTARY_MAX_FILES", "3"))
SUPPLEMENTARY_MAX_CHARS = int(os.getenv("SUPPLEMENTARY_MAX_CHARS", "200000"))

# Figure extraction / vision analysis
# Phase 1: PMC figure metadata extraction + Gemini multimodal gene discovery
ENABLE_FIGURE_ANALYSIS = os.getenv("ENABLE_FIGURE_ANALYSIS", "true").lower() == "true"
FIGURE_MAX_IMAGES_PER_PAPER = int(os.getenv("FIGURE_MAX_IMAGES_PER_PAPER", "3"))
FIGURE_IMAGE_MAX_BYTES = int(os.getenv("FIGURE_IMAGE_MAX_BYTES", str(5 * 1024 * 1024)))  # 5 MB

# --- PDF Extraction ---
ENABLE_PDF_OCR = os.getenv("ENABLE_PDF_OCR", "false").lower() == "true"
PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(30 * 1024 * 1024)))  # 30 MB
PDFM_CHAR_MARGIN = float(os.getenv("PDFM_CHAR_MARGIN", "2.0"))
PDFM_LINE_MARGIN = float(os.getenv("PDFM_LINE_MARGIN", "0.5"))
PDFM_WORD_MARGIN = float(os.getenv("PDFM_WORD_MARGIN", "0.1"))

GEMINI_CONFIG = {
    'gene_extraction_model': os.getenv("GEMINI_GENE_EXTRACTION_MODEL", "gemini-3-flash-preview"),
    'data_extraction_model': os.getenv("GEMINI_DATA_EXTRACTION_MODEL", "gemini-3-flash-preview"),
    'temperature': 0.0
}

# --- Additional Limits ---
MAX_MANDATORY = 50  # Hard cap on total mandatory PMIDs to prevent overload

# --- Hybrid Pipeline Configuration ---
# PubTator extraction for high-precision NER-based gene discovery
ENABLE_PUBTATOR_EXTRACTION = os.getenv("ENABLE_PUBTATOR_EXTRACTION", "true").lower() == "true"
PUBTATOR_BATCH_SIZE = int(os.getenv("PUBTATOR_BATCH_SIZE", "10"))

# NCBI Gene enrichment for metadata (full names, aliases, chromosomes)
ENABLE_NCBI_ENRICHMENT = os.getenv("ENABLE_NCBI_ENRICHMENT", "true").lower() == "true"
NCBI_API_KEY = os.getenv("NCBI_API_KEY")  # Optional: increases rate limits

# --- Gene Validation Heuristics ---
GENE_VALIDATION_MIN_CONFIDENCE = 0.4  # Minimum confidence score for gene validation (0.0-1.0)
ENABLE_GENE_VALIDATION = True  # Enable/disable gene validation heuristics

# Trust-gap hardening
# Deterministic candidate seeding + strict final gate for user-facing rows
ENABLE_DETERMINISTIC_CANDIDATES = os.getenv("ENABLE_DETERMINISTIC_CANDIDATES", "true").lower() == "true"
DETERMINISTIC_MAX_CANDIDATES = int(os.getenv("DETERMINISTIC_MAX_CANDIDATES", "120"))
DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY = os.getenv(
    "DETERMINISTIC_REQUIRE_CORROBORATION_FOR_GENE_ONLY", "true"
).lower() == "true"
ENABLE_BIOMARKER_NORMALIZATION = os.getenv("ENABLE_BIOMARKER_NORMALIZATION", "true").lower() == "true"
ENABLE_STRICT_VALIDATION_GATE = os.getenv("ENABLE_STRICT_VALIDATION_GATE", "true").lower() == "true"
FINAL_VALIDATION_MIN_CONFIDENCE = float(os.getenv("FINAL_VALIDATION_MIN_CONFIDENCE", "0.7"))
ENABLE_EVIDENCE_BACKFILL = os.getenv("ENABLE_EVIDENCE_BACKFILL", "true").lower() == "true"
EVIDENCE_SNIPPET_MAX_CHARS = int(os.getenv("EVIDENCE_SNIPPET_MAX_CHARS", "240"))
ENABLE_STRICT_EVIDENCE_GATE = os.getenv("ENABLE_STRICT_EVIDENCE_GATE", "true").lower() == "true"

# Biotype filtering: only protein-coding genes pass validation by default.
# Set to "false" for non-coding RNA studies (lncRNA, miRNA) where non-coding genes are expected.
VALIDATE_PROTEIN_CODING_ONLY = os.getenv("VALIDATE_PROTEIN_CODING_ONLY", "true").lower() == "true"
EVIDENCE_MIN_NONEMPTY_CELLS = int(os.getenv("EVIDENCE_MIN_NONEMPTY_CELLS", "1"))
# Per-source evidence gate thresholds.
# LLM-extracted rows carry inherent trust (the LLM translation itself is evidence).
# Set to 0 to allow LLM rows through even when backfill found nothing.
EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT = int(os.getenv("EVIDENCE_MIN_NONEMPTY_CELLS_LLM_TEXT", "0"))
# Deterministic-lexicon rows are mechanically seeded and need actual content corroboration.
EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC = int(os.getenv("EVIDENCE_MIN_NONEMPTY_CELLS_DETERMINISTIC", "1"))

# --- Citation Validation Heuristics ---
ENABLE_CITATION_VALIDATION = True  # Enable/disable citation validation (semantic density matching enabled)
CITATION_MIN_CONFIDENCE = 0.7  # Minimum confidence for citation validation (0.0-1.0)
CITATION_MIN_LENGTH = 10  # Minimum citation length to be considered valid

# --- Context Window Limits ---
# Gemini model context window limits (in tokens, approximate)
GEMINI_FLASH_CONTEXT_LIMIT = 1000000  # flash models: ~1M tokens
GEMINI_PRO_CONTEXT_LIMIT = 2000000    # pro models: ~2M tokens

# Context window safety margins (percentage of limit to use)
CONTEXT_SAFETY_MARGIN = 0.8  # Use 80% of context limit to be safe

# Enable context window checking
ENABLE_CONTEXT_CHECKING = True

# --- AI Processing ---
# Per-paper timeout (in seconds) for AI analysis to avoid indefinite hangs
AI_PER_PAPER_TIMEOUT_SECONDS = int(os.getenv("AI_PER_PAPER_TIMEOUT_SECONDS", "600"))

# Number of persistent worker processes for AI analysis.
# Workers are pre-warmed (imports paid once), eliminating per-paper spawn overhead.
# Default 2: if one worker hangs on a timeout, the other keeps processing.
# Hard-capped at 4 to avoid excessive memory use on the user's local machine.
AI_WORKER_POOL_SIZE = int(os.getenv("AI_WORKER_POOL_SIZE", "2"))

# Overfetch factor: how many extra candidate papers to analyze relative to requested top_n_cited
# to increase the chance of returning the desired number of papers with results
ANALYSIS_OVERFETCH_FACTOR = int(os.getenv("ANALYSIS_OVERFETCH_FACTOR", "4"))

# --- Forensic Run Analytics ---
# Persist stage-by-stage artifacts (screening decisions, fetch outcomes, gate drops)
# in the debug artifact JSON for full pipeline traceability.
ENABLE_FORENSIC_ARTIFACTS = os.getenv("ENABLE_FORENSIC_ARTIFACTS", "true").lower() == "true"
FORENSIC_INCLUDE_SCREENING = os.getenv("FORENSIC_INCLUDE_SCREENING", "true").lower() == "true"
FORENSIC_INCLUDE_FETCH_OUTCOMES = os.getenv("FORENSIC_INCLUDE_FETCH_OUTCOMES", "true").lower() == "true"

# --- Table-Aware Citation ---
# When prose citation matching fails, fall back to structured table-cell verification.
ENABLE_TABLE_CITATIONS = os.getenv("ENABLE_TABLE_CITATIONS", "true").lower() == "true"
TABLE_MIN_DATA_CELLS = int(os.getenv("TABLE_MIN_DATA_CELLS", "4"))
TABLE_MAX_PER_PAPER = int(os.getenv("TABLE_MAX_PER_PAPER", "20"))

os.makedirs(OUTPUT_DIR, exist_ok=True)
