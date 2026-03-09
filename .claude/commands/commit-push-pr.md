---
allowed-tools: Bash(git checkout *), Bash(git add *), Bash(git status *), Bash(git diff *), Bash(git push *), Bash(git commit *), Bash(git branch *), Bash(git log *), Bash(gh pr create *)
description: Commit all changes, push branch, and open a PR
---

## Context

- Current branch: !`git branch --show-current`
- Git status: !`git status`
- Staged + unstaged diff: !`git diff HEAD`
- Recent commits for style reference: !`git log --oneline -5`

## Your task

1. If on `main` or `master`, create a feature branch first
2. Stage all relevant changes (prefer specific files over `git add .` to avoid committing secrets)
3. Write a commit message: imperative mood, ≤72 chars subject, body explains *why* not *what*
4. Commit, push with `-u origin <branch>`
5. Open a PR with `gh pr create` — title under 70 chars, body with Summary and Test plan sections

Do all steps in a single response. Do not ask for confirmation.
