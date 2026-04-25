# Parser Ground Truth Comparison

Browser-visible PMC article pages were used as a reference for three OA PMIDs.
The browser reference counts visible `main article` text, so character and word
counts include metadata and page-visible article chrome. Parser text is expected
to be shorter because ResearchShop feeds a cleaner extraction to the LLM.
Figure URL downloadability is tracked separately in
`docs/pipeline/reports/figure-download-validation.md`.

## Browser Reference

| PMID | PMCID | Browser source | Chars | Words | Figures | Tables | Results hits | Table hits | Figure hits |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 36552004 | PMC9776003 | PMC page | 28,990 | 4,682 | 0 | 3 | 6 | 6 | 0 |
| 41169353 | PMC12568354 | PMC printable page | 82,255 | 12,257 | 6 | 2 | 14 | 10 | 35 |
| 41017238 | PMC12477333 | PMC page | 94,522 | 13,930 | 2 | 5 | 3 | 11 | 5 |

## Parser Comparison

Mode names:

- **current implementation**: production extractor after the ground-truth fix.
  It uses `pubmed_parser` for body paragraphs, keeps ResearchShop abstract and
  table extraction, filters non-image `pubmed_parser` figure refs, and merges
  valid `pubmed_parser` figure metadata with ResearchShop figure metadata.
- **legacy pure ResearchShop parser**: the pre-adapter parser path using only
  ResearchShop's JATS body, table, and figure traversal.
- **old hybrid (pre-merge)**: the first adapter version. It used
  `pubmed_parser` body text and accepted `pubmed_parser` figures as an
  exclusive replacement whenever at least one figure was returned.
- **pubmed_parser fullish**: experimental comparison using as much
  `pubmed_parser` output as practical for this use case; not production.

| PMID | Mode | Chars | Words | Figures | Tables | Results hits | Table hits | Figure hits |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 36552004 | **current implementation** | 17,585 | 2,707 | 0 | 3 | 6 | 12 | 0 |
| 36552004 | legacy pure ResearchShop parser | 17,005 | 2,686 | 0 | 3 | 6 | 12 | 0 |
| 36552004 | old hybrid (pre-merge) | 17,585 | 2,707 | 0 | 3 | 5 | 12 | 0 |
| 36552004 | pubmed_parser fullish | 12,283 | 1,821 | 0 | 0 | 5 | 3 | 0 |
| 41169353 | **current implementation** | 66,386 | 9,661 | 6 | 2 | 15 | 9 | 22 |
| 41169353 | legacy pure ResearchShop parser | 59,572 | 8,871 | 6 | 2 | 12 | 14 | 41 |
| 41169353 | old hybrid (pre-merge) | 59,888 | 8,719 | 1 | 2 | 12 | 6 | 2 |
| 41169353 | pubmed_parser fullish | 59,385 | 8,645 | 1 | 2 | 13 | 4 | 2 |
| 41017238 | **current implementation** | 63,226 | 8,651 | 2 | 5 | 9 | 22 | 7 |
| 41017238 | legacy pure ResearchShop parser | 54,582 | 8,014 | 2 | 5 | 0 | 21 | 7 |
| 41017238 | old hybrid (pre-merge) | 62,121 | 8,506 | 1 | 5 | 0 | 21 | 5 |
| 41017238 | pubmed_parser fullish | 59,120 | 8,067 | 1 | 5 | 0 | 16 | 5 |

## Interpretation

- Table counts: ResearchShop's current table parser matches the browser reference
  for all three PMIDs. `pubmed_parser` misses the 36552004 tables.
- Figure counts: the current implementation matches the browser reference for
  all three PMIDs. The old hybrid and fullish `pubmed_parser` modes
  under-counted figures on figure-heavy papers.
- Text volume: hybrid body text is comparable to pure ResearchShop extraction,
  while fullish `pubmed_parser` can be shorter when tables are missed.
- Action taken: hybrid extraction now merges `pubmed_parser` figure metadata
  with the existing ResearchShop figure parser instead of using
  `pubmed_parser` as an exclusive replacement whenever it returns at least one
  figure. Non-image `pubmed_parser` graphic refs such as `float` and `anchor`
  are ignored so they do not create duplicate pseudo-figures.
