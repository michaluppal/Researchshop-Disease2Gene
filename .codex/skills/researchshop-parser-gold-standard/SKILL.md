---
name: researchshop-parser-gold-standard
description: Validate ResearchShop PMC/PubMed parsing against browser gold standards. Use when checking parser changes, pubmed_parser integration, PMC full-text extraction, table extraction, figure metadata, figure URL downloadability, CDN image fetching, or reports comparing current ResearchShop extraction to browser-visible PMC pages.
---

# ResearchShop Parser Gold Standard

Use this skill to evaluate whether ResearchShop's current PMC extraction still matches the browser-visible article ground truth for text, table counts, figure counts, and figure downloadability.

## Workflow

1. Run the current parser comparison script:

   ```bash
   pipeline/.venv/bin/python3 pipeline/scripts/compare_pubmed_parser_ground_truth.py \
     --output docs/pipeline/reports/current-parser-ground-truth.md
   ```

2. Run the live figure download validation script:

   ```bash
   pipeline/.venv/bin/python3 pipeline/scripts/validate_figure_downloads.py \
     --output docs/pipeline/reports/figure-download-validation.md
   ```

   The maintained fixture must include at least one figure-rich PMID. Keep
   `41169353` in the run set unless replacing it with another manually verified
   multi-figure PMC article.

3. Use the Codex Browser / Browser Use skill for visual validation:

   - Open representative `resolved_url` values from `docs/pipeline/reports/figure-download-validation.md`.
   - Confirm the URL renders an actual scientific figure, not HTML, an error page, a placeholder, or a broken image.
   - Inspect at least one figure from the figure-rich PMID and record whether
     the image is readable enough for visual evidence review.
   - Capture what was inspected in the report or final summary.

4. If browser ground truth needs refreshing:

   - Open each PMC article URL from `pipeline/tests/fixtures/pmc_browser_ground_truth.json`.
   - Count visible article chars, words, table mentions, figure mentions, results mentions, table count, and figure count from the article page.
   - If a normal PMC page shows a browser check, do not bypass it. Try the official printable PMC URL (`?report=printable`) and note that source in the fixture/report.

5. Run verification after code changes:

   ```bash
   pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short
   git diff --check
   ```

## Interpretation Rules

- Figure/table count deltas should be `0` for the maintained gold-standard PMIDs unless the fixture is intentionally updated.
- Parser text can be shorter than browser text because ResearchShop feeds cleaner article content to the LLM.
- Figure URLs must download as `image/*` content and produce non-empty bytes.
- Browser figure spot checks should prioritize one complex multi-panel figure,
  one small/simple figure, and at least one figure from the maintained
  figure-rich PMID (`41169353` at the time of writing).
- Treat `pubmed_parser` as a parser/enrichment dependency, not as a new paper source.

## Core Artifacts

- Browser fixture: `pipeline/tests/fixtures/pmc_browser_ground_truth.json`
- Current parser report: `docs/pipeline/reports/current-parser-ground-truth.md`
- Historical parser comparison: `docs/pipeline/reports/parser-ground-truth-comparison.md`
- Figure download report: `docs/pipeline/reports/figure-download-validation.md`
- Parser comparison script: `pipeline/scripts/compare_pubmed_parser_ground_truth.py`
- Figure download script: `pipeline/scripts/validate_figure_downloads.py`

Read `references/browser-ground-truth.md` before updating fixture fields or adding PMIDs.
