# Current Parser vs Browser Ground Truth

Current ResearchShop extraction is compared to browser-visible PMC article references.
Parser text is expected to be cleaner and shorter than browser page text.

| PMID | PMCID | Source | Browser chars | Current chars | Browser words | Current words | Browser figures | Current figures | Browser tables | Current tables | Figure delta | Table delta |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 36552004 | PMC9776003 | PMC browser page | 28990 | 17585 | 4682 | 2707 | 0 | 0 | 3 | 3 | 0 | 0 |
| 41169353 | PMC12568354 | PMC printable browser page | 82255 | 66386 | 12257 | 9661 | 6 | 6 | 2 | 2 | 0 | 0 |
| 41017238 | PMC12477333 | PMC browser page | 94522 | 63226 | 13930 | 8651 | 2 | 2 | 5 | 5 | 0 | 0 |

## Hit Counts

| PMID | Browser results | Current results | Browser table hits | Current table hits | Browser figure hits | Current figure hits |
|---|---:|---:|---:|---:|---:|---:|
| 36552004 | 6 | 6 | 6 | 12 | 0 | 0 |
| 41169353 | 14 | 15 | 10 | 9 | 35 | 22 |
| 41017238 | 3 | 9 | 11 | 22 | 5 | 7 |
