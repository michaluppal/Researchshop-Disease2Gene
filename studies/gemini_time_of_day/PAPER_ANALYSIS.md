# Paper Analysis: Gemini Free-Tier WSL Experiment

This document summarizes the completed Windows/WSL Gemini free-tier time-of-day experiment for paper drafting. It is a tracked summary artifact; raw run folders and regenerated reports remain ignored by git.

## Source Artifacts

Primary session bundle:

- Run root: `studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/`
- Schedule: `studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/schedule.json`
- Driver log: `studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/driver.log`
- Per-slot manifests: `studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/hourXX/study_run.json`
- Regenerated report: `studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/reports/report.md`
- Regenerated CSV summaries: `batch_metrics.csv`, `paper_metrics.csv`, `time_block_summary.csv`, `descriptive_summary.csv`, `stability_metrics.csv`, `failure_events.csv`, `gate_events.csv`, `gate_by_run.csv`, `gate_by_pmid.csv`, and `gate_summary.csv`

The plan requested `session_summary.json`, but that file was not present in the copied WSL bundle. Aggregate consistency was therefore checked against the 24 `study_run.json` manifests and the regenerated `batch_metrics.csv`/summary CSVs.

Reports were regenerated locally from the copied full WSL bundle with:

```bash
pipeline/.venv/bin/python studies/gemini_time_of_day/analyze_results.py \
  --run-root studies/gemini_time_of_day/runs/session_20260609_0100_scheduler \
  --report-dir studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/reports
```

## Experiment Provenance

| Field | Value |
|---|---|
| Execution host | Windows laptop, ResearchShop checkout inside WSL Ubuntu |
| Local timezone | Europe/Warsaw |
| Planned schedule | 2026-06-09 01:00 through 2026-06-10 00:00, hourly |
| Manifest count | 24 `study_run.json` files |
| Git commit recorded in manifests | `f2ae56d2d01515c425abc67606fd4d036b48ef47` |
| Git dirty state | Mixed: early manifests `false`, later manifests `true`; treat as a provenance caveat |
| Model | `gemini-3.1-flash-lite` |
| Usage profile | `free` |
| Free-tier quota assumption | 500 requests/day, user-confirmed in AI Studio on 2026-06-08 |
| Corpus fingerprint | `75e48a979e5f9e8cc08b138a5e980e58ad886b3b5443203585b0d40fa6151707` |

Fixed corpus, in manifest order:

`36552004`, `35177862`, `23544013`, `34669946`, `41169353`, `41017238`, `39009607`, `34711957`, `29625052`, `41929321`

## Methods

Each formal slot used the same locked 10-PMID corpus. One batch was scheduled per local hour. The design therefore measures repeated processing of the same papers across time, rather than confounding time of day with paper difficulty.

Runtime settings were held fixed: `GEMINI_USAGE_PROFILE=free`, `PARALLEL_ANALYSIS=false`, `AI_WORKER_POOL_SIZE=1`, `GEMINI_MAX_CALLS_PER_PAPER=3`, `GEMINI_INTER_CALL_DELAY_SECONDS=6`, and `AI_PER_PAPER_TIMEOUT_SECONDS=600`. Optional figure analysis, PDF OCR, abstract-only discovery, and the second discovery pass were disabled. Pilot, stale, or unlocked-corpus runs were excluded; the analysis uses only the WSL session bundle above.

Failure classes distinguish Gemini/API capacity from upstream literature acquisition. Quota-limited rows, Gemini permission errors, and per-paper timeouts are Gemini/app operational failures. PubMed, metadata, and full-text acquisition failures are reported separately because they do not test Gemini free-tier capacity.

## Operational Results

Verdict from regenerated analyzer: **usable**.

| Metric | Result |
|---|---:|
| Attempted hourly slots | 24 |
| Complete 10-paper batches | 23 |
| Batch success rate | 95.8% |
| Paper slots | 240 |
| Completed papers | 230 |
| Quota-limited rows | 0 |
| Quota-limited papers | 0 |
| Quota warning count | 0 |
| Per-paper timeout count | 0 |
| Permission-denied count | 0 |
| Upstream metadata/full-text failure slots | 1 |
| Clean complete batches | 4 |
| Complete batches with recovered Gemini/API errors | 19 |
| Recovered model-unavailable/API events | 95 |
| Total Gemini API calls | 493 |
| Total prompt tokens | 7,299,416 |
| Total response tokens | 2,210,110 |
| Total Gemini tokens | 9,509,526 |
| Total emitted output rows | 7,007 |

Failure/recovery classes from the regenerated reports:

| Failure/recovery class | Runs |
|---|---:|
| `complete_clean` | 4 |
| `complete_recovered_gemini_errors` | 19 |
| `upstream_metadata_or_fulltext_failure` | 1 |

Per-slot summary from `batch_metrics.csv`/`failure_events.csv`:

| Run | Planned time | Time block | Completed papers | Runtime min | Calls | Recovered API events | Output rows | Class |
|---|---:|---|---:|---:|---:|---:|---:|---|
| hour01 | 01:00 | night | 10 | 13.3 | 22 | 4 | 319 | recovered Gemini/API |
| hour02 | 02:00 | night | 10 | 13.8 | 25 | 22 | 285 | recovered Gemini/API |
| hour03 | 03:00 | night | 10 | 11.5 | 22 | 24 | 306 | recovered Gemini/API |
| hour04 | 04:00 | night | 10 | 11.8 | 22 | 3 | 316 | recovered Gemini/API |
| hour05 | 05:00 | night | 10 | 11.6 | 22 | 2 | 313 | recovered Gemini/API |
| hour06 | 06:00 | morning | 10 | 11.2 | 21 | 1 | 319 | recovered Gemini/API |
| hour07 | 07:00 | morning | 0 | 0.1 | 0 | 0 | 0 | upstream metadata/full-text |
| hour08 | 08:00 | morning | 10 | 11.3 | 21 | 3 | 294 | recovered Gemini/API |
| hour09 | 09:00 | morning | 10 | 11.7 | 22 | 2 | 301 | recovered Gemini/API |
| hour10 | 10:00 | morning | 10 | 12.4 | 20 | 0 | 310 | clean |
| hour11 | 11:00 | morning | 10 | 15.3 | 24 | 5 | 316 | recovered Gemini/API |
| hour12 | 12:00 | afternoon | 10 | 11.6 | 23 | 3 | 300 | recovered Gemini/API |
| hour13 | 13:00 | afternoon | 10 | 10.3 | 20 | 13 | 299 | recovered Gemini/API |
| hour14 | 14:00 | afternoon | 10 | 10.6 | 21 | 1 | 294 | recovered Gemini/API |
| hour15 | 15:00 | afternoon | 10 | 11.5 | 21 | 1 | 303 | recovered Gemini/API |
| hour16 | 16:00 | afternoon | 10 | 11.6 | 20 | 0 | 311 | clean |
| hour17 | 17:00 | afternoon | 10 | 12.0 | 20 | 0 | 311 | clean |
| hour18 | 18:00 | evening | 10 | 13.4 | 22 | 3 | 307 | recovered Gemini/API |
| hour19 | 19:00 | evening | 10 | 13.8 | 21 | 1 | 293 | recovered Gemini/API |
| hour20 | 20:00 | evening | 10 | 9.7 | 20 | 1 | 305 | recovered Gemini/API |
| hour21 | 21:00 | evening | 10 | 9.0 | 20 | 2 | 318 | recovered Gemini/API |
| hour22 | 22:00 | evening | 10 | 8.5 | 20 | 0 | 299 | clean |
| hour23 | 23:00 | evening | 10 | 11.4 | 22 | 2 | 292 | recovered Gemini/API |
| hour00 | 00:00 | night | 10 | 12.3 | 22 | 2 | 296 | recovered Gemini/API |

## Runtime and Token Statistics

The table below uses successful 10-paper batches only, except where the scope explicitly says paper-level metrics from successful batches.

| Metric | Count | Mean | Median | SD | Min | Max | P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Batch runtime, min | 23 | 11.7 | 11.6 | 1.6 | 8.5 | 15.3 | 13.8 |
| Paper runtime, min | 230 | 1.1 | 0.6 | 1.4 | 0.1 | 6.2 | 4.9 |
| Batch Gemini calls | 23 | 21.4 | 21.0 | 1.3 | 20.0 | 25.0 | 24.0 |
| Paper Gemini calls | 230 | 2.1 | 2.0 | 0.4 | 2.0 | 3.0 | 3.0 |
| Batch prompt tokens | 23 | 317,366 | 324,560 | 15,266 | 264,450 | 324,669 | 324,669 |
| Batch response tokens | 23 | 96,092 | 98,901 | 12,458 | 69,491 | 113,689 | 111,545 |
| Batch total tokens | 23 | 413,458 | 422,304 | 25,103 | 333,941 | 438,249 | 436,105 |
| Paper total tokens | 230 | 41,346 | 37,869 | 23,550 | 12,830 | 112,148 | 100,500 |
| Batch output rows | 23 | 304.7 | 305.0 | 9.8 | 285.0 | 319.0 | 319.0 |
| Paper emitted rows | 230 | 30.5 | 29.5 | 20.8 | 1.0 | 73.0 | 68.0 |
| Paper strict-gate drops | 230 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| Paper citation-gate drops | 230 | 1.5 | 0.0 | 3.9 | 0.0 | 21.0 | 8.0 |

## Time-of-Day Comparison

Time blocks are Warsaw-local. The morning block contains the single upstream metadata/full-text failure at 07:00; all other blocks completed all six scheduled runs.

| Time block | Runs | Complete batches | Median runtime min | Median completion | Quota-limited runs | Upstream failures | Recovered API runs | Timeout runs | Median calls | Median total tokens | Median output rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| afternoon | 6 | 6 | 11.6 | 100% | 0 | 0 | 4 | 0 | 20.5 | 429,184 | 301.5 |
| evening | 6 | 6 | 10.5 | 100% | 0 | 0 | 5 | 0 | 20.5 | 421,019 | 302.0 |
| morning | 6 | 5 | 11.7 | 100% | 0 | 1 | 4 | 0 | 21.0 | 421,998 | 310.0 |
| night | 6 | 6 | 12.1 | 100% | 0 | 0 | 6 | 0 | 22.0 | 398,204 | 309.5 |

Median successful-batch runtime varied from 10.5 to 12.1 minutes across time blocks, far below the pre-specified 2x instability threshold. No time block showed quota-limited rows or per-paper timeouts.

## Output Stability

Overall stability from `stability_metrics.csv`:

| Stability metric | Result |
|---|---:|
| Median per-PMID emitted-row CV | 0.053 |
| Median per-PMID gene-set Jaccard | 0.953 |
| Median per-PMID gene-variant Jaccard | 1.000 |

Per-PMID stability summary:

| PMID | Runs | Mean rows | CV rows | Gene Jaccard | Gene-variant Jaccard | Mean citation drops |
|---|---:|---:|---:|---:|---:|---:|
| 23544013 | 23 | 26.0 | 0.050 | 0.955 | 0.917 | 0.5 |
| 29625052 | 23 | 53.6 | 0.057 | 0.934 | 0.970 | 2.4 |
| 34669946 | 23 | 1.0 | 0.000 | 1.000 | 1.000 | 0.0 |
| 34711957 | 23 | 12.0 | 0.000 | 1.000 | 1.000 | 0.0 |
| 35177862 | 23 | 64.0 | 0.133 | 0.861 | 1.000 | 9.0 |
| 36552004 | 23 | 1.9 | 0.151 | 0.913 | 0.913 | 1.1 |
| 39009607 | 23 | 41.9 | 0.016 | 0.992 | 1.000 | 0.1 |
| 41017238 | 23 | 38.0 | 0.058 | 0.951 | 1.000 | 0.2 |
| 41169353 | 23 | 20.3 | 0.082 | 0.913 | 1.000 | 2.0 |
| 41929321 | 23 | 46.0 | 0.000 | 1.000 | 1.000 | 0.0 |

Interpretation: output row counts were not perfectly identical, especially for PMIDs with more extracted rows and citation-gate drops, but gene-level and gene-variant-level sets were highly stable across repeated runs.

## Mechanical Gate Dispositions

The gate analysis uses two independent statistical units. Candidate dispositions describe records evaluated during candidate validation. Row dispositions describe final export decisions after row construction. The counts therefore must not be presented as one continuous attrition funnel, and neither unit is an expert correctness label.

| Unit | Recorded disposition | Count |
|---|---|---:|
| Candidate | Evaluated | 8,570 |
| Candidate | Retained | 7,259 |
| Candidate | Rejected: uncorroborated deterministic candidate | 1,219 |
| Candidate | Rejected: low confidence | 69 |
| Candidate | Rejected: ungrounded | 23 |
| Row | Final decisions recorded | 7,360 |
| Row | Emitted to the primary export | 7,007 |
| Row | Excluded by the citation gate | 353 |
| Row | Excluded by the strict confidence gate | 0 |

Across the 23 successful batches, candidate validation rejected 1,311 of 8,570 candidate records (15.3%). Most were deterministic candidates without corroborating source context. Separately, the final row stage emitted 7,007 of 7,360 recorded row decisions (95.2%); all 353 recorded row exclusions occurred at the citation gate, and none occurred at the final strict-confidence gate. These results quantify how often the implemented checks changed pipeline output. They do not show whether accepted or rejected findings were biologically correct, which requires expert adjudication.

Generated gate-analysis artifacts:

- `runs/session_20260609_0100_scheduler/reports/gate_events.csv`
- `runs/session_20260609_0100_scheduler/reports/gate_by_run.csv`
- `runs/session_20260609_0100_scheduler/reports/gate_by_pmid.csv`
- `runs/session_20260609_0100_scheduler/reports/gate_summary.csv`

## Numerical-Preservation Gate

Post-hoc analysis of the same WSL session found that numerical preservation was triggered 23 times across 17,854 citation validations. The events affected 12 rows in 8 of 24 hourly batches. Three rows were excluded from the primary export with a numeric-mismatch citation-gate signal; the remaining events were retained in exported metadata because another citation or validation path kept the row reviewable. This supports the intended role of the check: catching quantitative drift in LLM-provided evidence quotes without turning most citation-validation failures into export-blocking events.

| Metric | Value |
|---|---:|
| Hourly batches analyzed | 24 |
| Total citation validations | 17,854 |
| Numeric-bearing citations | 14 |
| Numeric mismatch events | 23 |
| Affected rows | 12 |
| Batches with >=1 mismatch | 8 |
| Rows excluded from primary export | 3 |
| Rows removed only after numeric mismatch | 3 |
| Mean mismatches per 10-paper batch | 0.958 |
| Median mismatches per 10-paper batch | 0.0 |
| Mismatches per emitted row | 0.0033 |
| Mismatches per citation validation | 0.0013 |

Generated numeric-preservation artifacts:

- [Numeric-preservation report](reports/numeric_preservation_report.md)
- [Numeric-preservation events CSV](reports/numeric_preservation_events.csv)
- [Numeric-preservation PMID summary](reports/numeric_preservation_by_pmid.csv)
- [Numeric-preservation heatmap](reports/numeric_preservation_heatmap.svg)

## Linked Figures

Generated plots are available in the ignored session report folder:

- [Batch runtime by hour](runs/session_20260609_0100_scheduler/reports/plots/batch_runtime_by_hour.svg)
- [Gemini calls by hour](runs/session_20260609_0100_scheduler/reports/plots/gemini_calls_by_hour.svg)
- [Gemini tokens by hour](runs/session_20260609_0100_scheduler/reports/plots/gemini_tokens_by_hour.svg)
- [Output rows by hour](runs/session_20260609_0100_scheduler/reports/plots/output_rows_by_hour.svg)
- [Failure matrix](runs/session_20260609_0100_scheduler/reports/plots/failure_matrix.svg)
- [Runtime by time block](runs/session_20260609_0100_scheduler/reports/plots/runtime_by_time_block.svg)
- [Per-PMID output rows heatmap](runs/session_20260609_0100_scheduler/reports/plots/per_pmid_output_rows_heatmap.svg)
- [Numerical-preservation heatmap](reports/numeric_preservation_heatmap.svg)

## Paper-Ready Interpretation

Under this 24-hour WSL study design, Gemini free-tier operation was usable for a normal 10-paper ResearchShop batch. ResearchShop completed 23 of 24 hourly 10-paper batches (95.8%); the only incomplete slot was classified as an upstream metadata/full-text failure, not a Gemini quota, permission, or timeout failure. Successful batches had median runtime 11.6 minutes (p95 13.8), median 21 Gemini calls, and median 422,304 total Gemini tokens. No quota-limited rows, quota warnings, permission-denied errors, or per-paper timeouts occurred. Runtime varied modestly by time block (median 10.5-12.1 minutes), and output stability was high (median gene-set Jaccard 0.953; median gene-variant Jaccard 1.000). Recovered model-unavailable/API events were common, however, so the result supports free-tier usability only with retry handling and explicit failure reporting.

## Manuscript Insertion Candidate

Draft text, pending author review:

ResearchShop was also evaluated in a 24-hour operational free-tier study on a Windows/WSL laptop using a fixed 10-paper open-access corpus and hourly repeated runs with `gemini-3.1-flash-lite`. Of 24 scheduled hourly batches, 23 completed all 10 papers (95.8%); the single incomplete slot was due to upstream metadata/full-text acquisition rather than Gemini quota exhaustion. Successful batches had median runtime of 11.6 min (p95 13.8 min), used a median of 21 Gemini calls, and showed no quota-limited rows or per-paper timeouts. Across successful runs, candidate validation retained 7,259 of 8,570 candidate records, while final row decisions emitted 7,007 rows and excluded 353 at the citation gate. Output sets were stable across repeated runs, with median per-PMID gene-set Jaccard similarity of 0.953 and gene-variant Jaccard similarity of 1.000. These results support small-batch operational use under the tested configuration, provided that transient API unavailability is handled by retries and surfaced in the audit log; they do not estimate biological accuracy.

Small Section 4 table draft:

| Operational measure | Result |
|---|---:|
| Hourly 10-paper slots attempted | 24 |
| Complete 10-paper batches | 23/24 (95.8%) |
| Median successful-batch runtime | 11.6 min |
| P95 successful-batch runtime | 13.8 min |
| Median Gemini calls per successful batch | 21 |
| Quota-limited rows | 0 |
| Per-paper timeouts | 0 |
| Median gene-set Jaccard | 0.953 |
| Median gene-variant Jaccard | 1.000 |

## Limitations

- The experiment used one API project/key and one Windows laptop/home network; it does not measure cross-account or cross-region variability.
- The window covered one 24-hour period, not multiple days or multiple weeks.
- The 10-PMID corpus controls paper difficulty for time-of-day comparison but does not represent all biomedical literature.
- One incomplete slot was an upstream metadata/full-text failure, which is separate from Gemini capacity and should not be counted as quota exhaustion.
- Recovered model-unavailable/API events occurred in 19 of 23 complete batches, so retry behavior is part of the measured system, not a negligible implementation detail.
- Stability metrics measure output-row, gene-set, and gene-variant-set consistency. They are not a clinical correctness or biological validity benchmark.
- Later manifests recorded `git_dirty: true`; the commit hash is fixed, but the dirty-state flag should be disclosed if these numbers are used as final paper evidence.
