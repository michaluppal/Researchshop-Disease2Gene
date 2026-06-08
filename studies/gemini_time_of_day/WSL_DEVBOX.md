# WSL Devbox Hourly Study Runbook

Use this runbook on the Windows laptop inside WSL Ubuntu.

## 1. Sync the Checkout

```bash
ssh agentbox
wsl -d Ubuntu
cd ~/projects/Researchshop-Disease2Gene
git pull --ff-only
```

## 2. Create the Local Secret File

Create `/home/student/projects/Researchshop-Disease2Gene/.env`:

```bash
GEMINI_API_KEY=<the Gemini key provided for the Windows study>
ENTREZ_EMAIL=michal.uppal1@gmail.com
```

Then lock down permissions:

```bash
chmod 600 .env
```

The root `.gitignore` excludes `.env`; do not commit this file.

## 3. Verify the Environment

```bash
date
npm run typecheck
npm test
npm run build
pipeline/.venv/bin/python -m pytest pipeline/tests/test_gemini_time_study.py
```

## 4. Start the Hourly Study

When launching remotely over SSH, use a Windows-owned `wsl.exe` process. This
keeps the WSL workload alive after the SSH command exits:

```powershell
cmd /c start "ResearchShop Gemini Study" wsl -d Ubuntu --cd /home/student/projects/Researchshop-Disease2Gene -- bash -lc "pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py --hours 24 --captured-by 'WSL Windows laptop'"
```

If you are sitting at the Windows laptop in an interactive WSL terminal, `tmux`
is also acceptable:

```bash
tmux new -s rs-gemini-study
pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py \
  --hours 24 \
  --captured-by "WSL Windows laptop"
```

Detach with `Ctrl-b d`. Reattach with:

```bash
tmux attach -t rs-gemini-study
```

If neither of those is available:

```bash
nohup pipeline/.venv/bin/python studies/gemini_time_of_day/run_hourly_study.py \
  --hours 24 \
  --captured-by "WSL Windows laptop" \
  > studies/gemini_time_of_day/runs/wsl_hourly_nohup.log 2>&1 &
```

## 5. Outputs

The driver creates a runtime-only session directory:

```text
studies/gemini_time_of_day/runs/session_<YYYYMMDD_HHMM>/
```

Important files:

- `driver.log`
- `schedule.json`
- `session_summary.json`
- `reports/report.md`
- `reports/batch_metrics.csv`
- `reports/paper_metrics.csv`
- `reports/time_block_summary.csv`
- `hourXX/study_run.json` for every attempted run

The driver skips slots when the current Pacific-reset quota window approaches
the configured Gemini call cap, stops early if quota-limited rows appear, and
stops if repeated failures indicate that the API is not usable during the
session.
