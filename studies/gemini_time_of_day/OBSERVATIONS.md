# Gemini Free-Tier Study Observations

## 2026-06-05/06 CLI Smoke Run

- Run ID: `hour23`
- Local start: `2026-06-05T23:44:56+02:00`
- Local end: `2026-06-05T23:59:02+02:00`
- Runtime: 845.668 seconds
- Gemini model: `gemini-2.5-flash-lite`
- Gemini API calls: 18
- Quota-limited papers/rows: 0 / 0
- Timeouts: 0
- Output rows: 371
- Caveat: this was a preliminary run on the original corpus. PMID `36929942`
  failed the CLI full-text fetch path and was replaced before locking the
  revised corpus.

## 2026-06-06 Replacement-PMID Pilot

- Candidate PMID: `39009607`
- PMC source: `PMC11250857`
- CLI full-text fetch: succeeded with 61,679 chars and quality 0.90.
- Gemini result: quota-limited after the preceding 10-paper batch.
- Observed quota error: `generate_content_free_tier_requests`, daily free-tier
  limit 20 for `gemini-2.5-flash-lite`.

## Design Consequence

The active project cannot support hourly or 30-minute repeated 10-paper batches
with this model and key. A single 10-paper batch consumed 18 of 20 daily
free-tier requests. The formal study should therefore use one 10-paper batch per
quota-reset window and rotate the scheduled local start time across days.

## 2026-06-06 Schedule Adjustment

The formal schedule was changed from an hourly template to a 12-run
quota-window schedule: 4 local time blocks x 3 repeats, with one batch per
Pacific-midnight reset window. The locked-corpus formal report currently has no
valid runs because the only completed 10-paper batch used the preliminary corpus
before PMID `36929942` was replaced.

## 2026-06-08 Model Switch

AI Studio showed an active free-tier limit of 500 requests/day for
`gemini-3.1-flash-lite`, so the active study condition was switched from
`gemini-2.5-flash-lite` to `gemini-3.1-flash-lite`. The schedule was changed
back to hourly 24-hour sampling. With the observed 18 Gemini calls per 10-paper
batch, 24 hourly runs are expected to use about 432 requests, below the
500-request daily limit if call counts stay stable.
