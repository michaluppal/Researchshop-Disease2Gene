# ResearchShop v1.0.2

This release adds reproducible operational analysis for the completed
24-hour Gemini free-tier study and an editorial manuscript prepared for
coauthor review.

## Study Results

- 24 hourly 10-PMID batches were attempted; 23 completed.
- The 07:00 batch failed during upstream full-text acquisition, not because
  of Gemini quota exhaustion.
- No quota-limited rows or per-paper timeouts were recorded.
- Candidate validation retained 7,259 of 8,570 candidate records.
- Final row decisions emitted 7,007 rows and excluded 353 at the citation
  gate; no strict-gate drops were recorded.
- The logs contain 95 recovered model-unavailable/API events. These are
  recovery log events and are not assumed to represent 95 unique failed
  HTTP requests.

The study used `gemini-3.1-flash-lite` as a configurable model override. The
released application continues to default to `gemini-2.5-flash-lite`.

## Scope And Provenance

This is an operational reliability and output-stability study. It used no
expert-labelled reference set and does not estimate biological precision,
recall, F1, clinical validity, or research usefulness. The editorial
manuscript contains a visibly pending expert-assessment template for the
KRAS example; no finding was selected or classified by AI.

The WSL manifests record commit
`f2ae56d2d01515c425abc67606fd4d036b48ef47` and both clean and dirty
worktree states. The commit identifies the base source, but uncommitted
changes present during later runs cannot be reconstructed from this bundle.

## Artifacts

- Unsigned macOS ARM64 disk image.
- Sanitized reproducibility bundle with aggregate, per-run, and per-PMID
  reports, plots, corpus identifiers, provenance, and internal checksums.
- Release-level SHA-256 checksums.
