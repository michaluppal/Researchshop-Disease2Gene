# ResearchShop Gemini Free-Tier Reproducibility Bundle

Release: `v1.0.2`

This sanitized bundle contains aggregate results from the completed 24-hour
Windows/WSL operational study. The same locked 10-PMID corpus was processed
once per Warsaw-local hour with `gemini-3.1-flash-lite`.

## Statistical Units

- Candidate dispositions describe candidate records evaluated before row
  construction.
- Row dispositions describe final export decisions. Their denominator is
  independent of the candidate-record denominator.
- Recovered API events are log events matched by the study harness; they are
  not guaranteed to be unique failed HTTP requests.
- Stability statistics compare repeated outputs from the same PMIDs.

## Exclusions

The bundle excludes API keys, email addresses, personal filesystem paths,
downloaded article text, citation-bearing result rows, workbooks, and raw
debug artifacts. It contains no expert annotation and does not estimate
biological precision, recall, F1, or clinical validity.

## Regeneration

The aggregate reports were generated with:

```bash
python studies/gemini_time_of_day/analyze_results.py \
  --run-root studies/gemini_time_of_day/runs/session_20260609_0100_scheduler \
  --report-dir studies/gemini_time_of_day/runs/session_20260609_0100_scheduler/reports
```

`CHECKSUMS.sha256` verifies every included file.
