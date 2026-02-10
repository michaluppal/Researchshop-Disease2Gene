import os
from pathlib import Path

# --- Output Directory ---
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/output")
Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL", "your.email@example.com")
ENTREZ_API_KEY = os.getenv("ENTREZ_API_KEY")  # Optional: for faster NCBI API access

# --- Publication Type Filters ---
# List of publication types to exclude from PubMed searches
EXCLUDED_PUBLICATION_TYPES = [
    "Review",
    "Meta-Analysis",
    "Systematic Review",
    "Editorial",
    "Comment",
    "Letter",
    "News",
    "Guideline",
    "Case Reports",
]

# --- PubMed Search Configuration ---
PUBMED_SORT = os.getenv(
    "PUBMED_SORT", "date"
)  # Sort by date for determinism (was: "relevance")

# --- HTTP client/networking ---
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
REQUEST_RETRIES = int(os.getenv("REQUEST_RETRIES", "3"))
BACKOFF_FACTOR = float(os.getenv("BACKOFF_FACTOR", "0.5"))
FETCH_MAX_WORKERS = int(
    os.getenv("FETCH_MAX_WORKERS", "3")
)  # Concurrency for fetching (reduced to avoid overwhelming slow sites)
# Timeout for each full-text extraction thread (seconds) - prevents indefinite hangs
FETCH_THREAD_TIMEOUT = int(
    os.getenv("FETCH_THREAD_TIMEOUT", "120")
)  # 2 minutes per PMID (reduced from 5 minutes to fail faster on stuck requests)

# --- Unpaywall (for OA discovery) ---
UNPAYWALL_EMAIL = os.getenv("UNPAYWALL_EMAIL")

# --- Gene Extraction Batching ---
# When a paper has more than this many genes, process detailed extraction in batches
# to avoid API overload. Default: 8 genes per batch (safe for most papers)
GENE_BATCH_THRESHOLD = int(os.getenv("GENE_BATCH_THRESHOLD", "8"))

# --- Gemini AI Model Configuration ---
# Using Flash models (non-lite) to potentially avoid rate limiting issues
# - Gemini 2.0 Flash: Model for gene discovery
# - Gemini 2.5 Flash: Model for detailed attribute extraction
GEMINI_CONFIG = {
    "gene_extraction_model": "gemini-2.0-flash",  # Model for gene discovery
    "data_extraction_model": "gemini-2.5-flash",  # Model for detailed extraction
    "temperature": 0.1,  # Lowered from 0.3 for better determinism
}


# --- Gemini API Rate Limiting (Free Tier Limits) ---
# Rate limits per model based on official free tier limits
# Source: Google Gemini API documentation
GEMINI_RATE_LIMITS = {
    "gemini-2.0-flash-lite": {
        "rpm": 30,  # Requests per minute
        "tpm": 1000000,  # Tokens per minute
        "rpd": 200,  # Requests per day
    },
    "gemini-2.5-flash-lite": {
        "rpm": 15,  # Requests per minute
        "tpm": 250000,  # Tokens per minute (corrected from 1M)
        "rpd": 1000,  # Requests per day (corrected from 1500)
    },
    "gemini-2.0-flash": {
        "rpm": 15,  # Requests per minute
        "tpm": 1000000,  # Tokens per minute
        "rpd": 200,  # Requests per day
    },
    "gemini-2.5-flash": {
        "rpm": 10,  # Requests per minute
        "tpm": 250000,  # Tokens per minute
        "rpd": 250,  # Requests per day
    },
}

# Rate limiting implementation
GEMINI_ENABLE_RATE_LIMITING = (
    os.getenv("GEMINI_ENABLE_RATE_LIMITING", "true").lower() == "true"
)
GEMINI_RATE_LIMIT_SAFETY_MARGIN = 0.9  # Use 90% of limits to be safe

# --- Additional Limits ---
MAX_MANDATORY = 50  # Hard cap on total mandatory PMIDs to prevent overload

# --- Gene Validation Heuristics ---
GENE_VALIDATION_MIN_CONFIDENCE = (
    0.4  # Minimum confidence score for gene validation (0.0-1.0)
)
ENABLE_GENE_VALIDATION = True  # Enable/disable gene validation heuristics

# --- Citation Validation Heuristics ---
ENABLE_CITATION_VALIDATION = (
    False  # Enable/disable citation validation (disabled by default to reduce clutter)
)
CITATION_MIN_CONFIDENCE = 0.7  # Minimum confidence for citation validation (0.0-1.0)
CITATION_MIN_LENGTH = 10  # Minimum citation length to be considered valid

# --- Context Window Limits ---
# Gemini model context window limits (in tokens, approximate)
# Updated for new models:
# - Gemini 2.5 Flash: ~1M tokens (same as 2.5 Flash-Lite)
# - Gemini 2.0 Flash-Lite: ~1M tokens
GEMINI_FLASH_CONTEXT_LIMIT = 1000000  # gemini-2.5-flash: ~1M tokens
GEMINI_FLASH_LITE_CONTEXT_LIMIT = 1000000  # gemini-2.0-flash-lite: ~1M tokens

# --- Context Window Safety Margins ---
# Use only 90% of context limit to leave room for prompt overhead
CONTEXT_SAFETY_MARGIN = 0.9

# --- AI Analysis Timeout ---
AI_PER_PAPER_TIMEOUT_SECONDS = int(
    os.getenv("AI_PER_PAPER_TIMEOUT_SECONDS", "600")
)  # 10 minutes per paper (increased from 5 min for papers with many genes)

# --- Context Validation ---
ENABLE_CONTEXT_CHECKING = os.getenv("ENABLE_CONTEXT_CHECKING", "true").lower() == "true"

# --- User-Defined Column Limits ---
# Recommended: 5-10 columns for best quality
# Maximum recommended: 15 columns (quality degrades beyond this)
MAX_USER_COLUMNS = int(os.getenv("MAX_USER_COLUMNS", "15"))


def validate_runtime_configuration():
    """Validate that required configuration is present."""
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please set it in your environment or .env file."
        )
    if not ENTREZ_EMAIL or ENTREZ_EMAIL == "your.email@example.com":
        raise ValueError(
            "ENTREZ_EMAIL is not set or is using the default value. Please set it in your environment or .env file."
        )
