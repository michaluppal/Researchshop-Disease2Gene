# Commit, Push, PR Recipe

Use when the user asks to commit, push, and prepare or open a pull request.

## Context

- Branch: `git branch --show-current`
- Status: `git status`
- Diff: `git diff HEAD`
- Recent message style: `git log --oneline -5`

## Steps

1. If on `main` or `master`, create a feature branch first.
2. Stage only relevant files. Prefer explicit paths over `git add .`.
3. Write an imperative commit subject no longer than 72 characters.
4. In the body, explain why the change exists and mention validation.
5. Commit.
6. Push with `git push -u origin <branch>`.
7. If requested and `gh` is available, create a PR with a title under 70 characters and a body containing Summary and Test plan sections.

Do not include secrets, local build artifacts, or unrelated generated files.
