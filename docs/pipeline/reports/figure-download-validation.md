# Figure Download Validation

Live validation that current extracted figure metadata resolves to downloadable image bytes.

| PMID | PMCID | Figure | Downloadable | MIME | Bytes | Resolved URL |
|---|---|---|---|---|---:|---|
| 36552004 | PMC9776003 |  | n/a |  |  |  |
| 41169353 | PMC12568354 | Figure 1 | yes | image/jpeg | 109801 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/c1ad821cf483/fimmu-16-1670488-g001.jpg |
| 41169353 | PMC12568354 | Figure 2 | yes | image/jpeg | 129603 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/287859707591/fimmu-16-1670488-g002.jpg |
| 41169353 | PMC12568354 | Figure 3 | yes | image/jpeg | 278900 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/c5f43320f539/fimmu-16-1670488-g003.jpg |
| 41169353 | PMC12568354 | Figure 4 | yes | image/jpeg | 108396 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/0bee19e721f8/fimmu-16-1670488-g004.jpg |
| 41169353 | PMC12568354 | Figure 5 | yes | image/jpeg | 119738 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/e4c3360590a7/fimmu-16-1670488-g005.jpg |
| 41169353 | PMC12568354 | Figure 6 | yes | image/jpeg | 109978 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/57b9/12568354/f06484c939e2/fimmu-16-1670488-g006.jpg |
| 41017238 | PMC12477333 | Figure 1 | yes | image/jpeg | 114200 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/7c43/12477333/d12de1c1b1d9/IID3-13-e70267-g002.jpg |
| 41017238 | PMC12477333 | Figure 2 | yes | image/jpeg | 92874 | https://cdn.ncbi.nlm.nih.gov/pmc/blobs/7c43/12477333/14ae3671b3c3/IID3-13-e70267-g001.jpg |

## Browser Spot Check

- `41169353` / Figure 3 opened as a 762 x 969 JPEG with readable multi-panel
  pathway/bubble-plot content.
- `41017238` / Figure 2 opened as a 608 x 361 JPEG with readable schematic
  labels.
- `36552004` has no extracted figures in the current implementation, matching
  the browser ground truth.

## Implementation Note

The current downloader first tries XML-derived figure URL candidates, then
resolves PMC CDN blob URLs from the article page. CDN URL discovery is cached
per article page during a run, reducing repeated HTML fetches and improving
reliability for multi-figure papers.
