# Audit Entry Recipe

Use this to add a properly formatted finding to `docs/audit/AUDIT.md`.

## Gather Context

- Date: `date +%Y-%m-%d`
- Existing entry numbers: `rg "^(F|W)[0-9]+:" docs/audit/AUDIT.md`

## Confirmed Bug Format

```markdown
FN: [short title]
- Description: what the bug is
- Impact: what goes wrong
- Root cause: why it happens
- Affected files: module(s)
- Fix: what was changed, or PENDING if not yet fixed
- Medical accuracy note: patient-facing or scientific accuracy risk, when relevant
```

## Design Tradeoff / Warning Format

```markdown
WN: [short title]
- Description: what the tradeoff is
- Risk: what could go wrong
- Mitigation: why it is acceptable or what guards exist
- Affected files: module(s)
- Status: Accepted / Monitor / Revisit when X
```

Rules:

- Never renumber existing entries.
- Add medical accuracy notes for anything that affects gene/variant extraction correctness.
- Update the "Last audited" date at the top of `docs/audit/AUDIT.md` when present.
- If the entry fixes an existing W-series warning, cross-reference it.
