# Gemini Free-Tier Time-of-Day Study

This directory contains a reproducible harness for measuring whether the Gemini
free tier is reliable for a fixed 10-paper ResearchShop batch, and whether
runtime or API failure rate changes by time of day.

## Goal

Evaluate whether ResearchShop can reliably process a fixed 10-paper
open-access batch using Google Gemini free-tier API access, and determine
whether performance or failure rate changes by time of day.

The paper-facing question is:

> Can a normal ResearchShop user process a 10-paper biomedical extraction batch
> reliably on the Gemini free tier, and does time of day materially affect
> runtime or API failure rate?

## Study Design

- Run the same 10 PMIDs in every formal batch.
- Run via the ResearchShop CLI harness so timings are scriptable and
  reproducible without GUI automation.
- Run repeated batches hourly across a 24-hour observation window.
- Use the 24-run schedule in `schedule.json`: 6 runs per time block, using
  Europe/Warsaw local time.
- Assign each run to a Europe/Warsaw time block during analysis:
  `night` (`00:00`-`05:59`), `morning` (`06:00`-`11:59`), `afternoon`
  (`12:00`-`17:59`), or `evening` (`18:00`-`23:59`).
- Keep the same Google project/API key for the whole study.
- Do not use the study API key for unrelated Gemini work during the study.
- If a batch is still running when the next interval arrives, skip the next
  scheduled run rather than overlapping batches.

The study condition is now `gemini-3.1-flash-lite`. On 2026-06-08, AI Studio
showed an active free-tier limit of 500 requests/day for this model. A previous
`gemini-2.5-flash-lite` pilot hit an observed 20 requests/day limit, so those
2.5 results remain documented as preliminary and are excluded from the formal
3.1 Flash-Lite report.

The runner forces the benchmark settings from the plan:

- `gemini-3.1-flash-lite`
- `GEMINI_USAGE_PROFILE=free`
- `PARALLEL_ANALYSIS=false`
- `AI_WORKER_POOL_SIZE=1`
- `GEMINI_MAX_CALLS_PER_PAPER=3`
- `GEMINI_INTER_CALL_DELAY_SECONDS=6`
- `AI_PER_PAPER_TIMEOUT_SECONDS=600`
- figure analysis, OCR, abstract discovery, and second-pass discovery disabled

## Files

- `corpus.json`: the fixed PMID manifest. It starts as unverified; replace any
  unsuitable candidate PMIDs and set `verified` to `true` only after pilot
  verification.
- `columns.json`: stable schema columns for every run.
- `schedule.json`: 24-hour hourly schedule with one run ID per local hour.
- `quota_snapshot.template.json`: copy this before each formal run and fill in
  the current AI Studio quota values.
- `run_study.py`: executes one pilot or scheduled batch.
- `analyze_results.py`: aggregates all completed `study_run.json` files.

Runtime outputs are ignored under `runs/` and `reports/`.

## Before Running

Confirm these are available in the shell that launches the runner:

```bash
export GEMINI_API_KEY="..."
export ENTREZ_EMAIL="you@example.com"
```

For the Windows/WSL devbox study, use `ENTREZ_EMAIL=michal.uppal1@gmail.com`.
See `WSL_DEVBOX.md` for the tmux-based unattended runbook.

For the Windows WSL devbox, use:

```bash
cat > .env <<'EOF'
GEMINI_API_KEY=...
ENTREZ_EMAIL=michal.uppal1@gmail.com
EOF
chmod 600 .env
```

`run_study.py` uses `pipeline/.venv/bin/python` for the pipeline when that
venv exists. To force a different interpreter, set:

```bash
export RESEARCHSHOP_PIPELINE_PYTHON="/path/to/python"
```

Before every formal run, copy and fill the quota snapshot:

```bash
cp studies/gemini_time_of_day/quota_snapshot.template.json \
  studies/gemini_time_of_day/runs/hour00_quota_snapshot.json
```

Record the visible AI Studio / Google Cloud quota values for RPM, TPM, and RPD.
Google documents Gemini limits as RPM, TPM, and RPD per project, with daily
quota reset at midnight Pacific time:

- <https://ai.google.dev/gemini-api/docs/rate-limits>
- <https://ai.google.dev/gemini-api/docs/pricing>

## Pilot

Run a small pilot before locking the corpus:

```bash
python3 studies/gemini_time_of_day/run_study.py \
  --pilot \
  --allow-unverified-corpus \
  --max-runtime-seconds 1800
```

Review the pilot output in `studies/gemini_time_of_day/runs/pilot/study_run.json`.
Replace any PMID that lacks stable full text or produces unusable output. Once
all 10 PMIDs are verified, set `verified` to `true` in `corpus.json`.

Formal manifests include a SHA-256 fingerprint of the exact PMID list used for
the run. The analyzer excludes old manifests whose fingerprint is missing or
does not match the current `corpus.json`, so preliminary runs made before corpus
lock do not contaminate the final report.

## Formal Runs

At each scheduled local time, run exactly one batch:

```bash
python3 studies/gemini_time_of_day/run_study.py \
  --run-id hour00 \
  --quota-snapshot studies/gemini_time_of_day/runs/hour00_quota_snapshot.json \
  --max-runtime-seconds 7200
```

Use the run IDs from `schedule.json`. Do not add 30-minute repeats unless AI
Studio shows enough active free-tier headroom for the measured calls-per-batch.
At the observed 22 calls per 10-paper validation batch, 24 hourly runs would use
roughly 528 total requests. The static midnight-start schedule splits these
across the 09:00 local quota reset, and the hourly WSL driver enforces
per-quota-window headroom. The runner writes:

- timestamped raw pipeline events
- the normal ResearchShop CSV/JSON/XLSX/debug artifacts
- `study_run.json`, the normalized study manifest

Formal runs refuse to start before their scheduled Europe/Warsaw time and refuse
to overwrite an existing `study_run.json`. Use `--allow-early-run` or
`--overwrite-run` only for intentional debugging, not for formal data
collection.

If you want to record the app-local usage counter manually, pass:

```bash
--usage-before 0 --usage-after 27
```

For each run, record that it was launched through the CLI harness, plus the
exact git commit, environment settings, and output paths captured in
`study_run.json`.

For the Windows laptop run, prefer the hourly driver:

```bash
pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py \
  --hours 24 \
  --captured-by "WSL Windows laptop"
```

## WSL Hourly Driver

When launching remotely over SSH, start the 24-hour study as a Windows-owned
`wsl.exe` process so it stays alive after SSH disconnects:

```powershell
cmd /c start "ResearchShop Gemini Study" wsl -d Ubuntu --cd /home/student/projects/Researchshop-Disease2Gene -- bash -lc "pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py --hours 24 --captured-by 'WSL Windows laptop'"
```

When using the Windows laptop interactively, `tmux` is also acceptable from the
WSL checkout:

```bash
cd /home/student/projects/Researchshop-Disease2Gene
git pull --ff-only
tmux new -s rs-gemini-study
pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py
```

The driver loads `.env`, generates a fresh ignored schedule under
`studies/gemini_time_of_day/runs/session_<YYYYMMDD_HHMM>/`, sleeps until each
scheduled local hour, skips late slots rather than overlapping, and writes
`driver.log`, per-run manifests, `session_summary.json`, and session-level
reports. Detach with `Ctrl-b d`; reattach with:

```bash
tmux attach -t rs-gemini-study
```

If `tmux` is unavailable, use:

```bash
nohup pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py \
  > studies/gemini_time_of_day/runs/study_driver.nohup.log 2>&1 &
```

For a first live validation batch only, run:

```bash
pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py --hours 1
```

## Analysis

After the formal observation window:

```bash
python3 studies/gemini_time_of_day/analyze_results.py
```

To audit preliminary or superseded-corpus runs separately, pass
`--include-unlocked-corpus-runs`.

This writes:

- `reports/batch_metrics.csv`
- `reports/paper_metrics.csv`
- `reports/time_block_summary.csv`
- `reports/report.md`

The report classifies the free tier as `usable`, `marginal`, or `not_usable`.

## Interpretation Criteria

Call the free tier `usable` when:

- At least 90% of batches complete all 10 papers without quota-limited rows.
- Median batch runtime is under 90 minutes.
- No time block has median runtime more than 2x another block.
- Output row counts remain roughly stable across repeated runs.
- Failures, if any, are rare and recoverable by rerun after quota reset.

Call it `marginal` when completion is 70-89%, or when runtimes are inconsistent
but most runs finish.

Call it `not_usable` when completion is below 70%, quota/rate-limit errors are
frequent, or 600-second per-paper timeouts are common.
