---
allowed-tools: Read, Edit
description: "Add a properly formatted entry to AUDIT.md. Usage: /audit-entry <brief description of the finding>"
---

## Context

- Today's date: !`date +%Y-%m-%d`
- Current AUDIT.md entry numbers (to determine next F/W number): !`grep -E "^(F|W)[0-9]+:" AUDIT.md | tail -20`

## Finding to document

$ARGUMENTS

## Your task

Add a new entry to `AUDIT.md` for the finding described above (or as I will describe if $ARGUMENTS is empty). Follow the established format strictly:

**For a confirmed bug (Fixed or Pending Fix):**
```
FN: [short title]
- Description: what the bug is
- Impact: what goes wrong (false gene results, silent data loss, incorrect output, etc.)
- Root cause: why it happens
- Affected files: module(s)
- Fix: what was changed, or "PENDING" if not yet fixed
- Medical accuracy note: if relevant, describe patient-facing or scientific accuracy risk
```

**For a design tradeoff/warning:**
```
WN: [short title]
- Description: what the tradeoff is
- Risk: what could go wrong
- Mitigation: why it's acceptable / what guards exist
- Affected files: module(s)
- Status: Accepted / Monitor / Revisit when X
```

Rules:
- Never renumber existing entries
- Add medical accuracy notes for anything that affects gene/variant extraction correctness
- Update the "Last audited" date at the top of AUDIT.md
- If the entry fixes an existing W-series warning, cross-reference it
