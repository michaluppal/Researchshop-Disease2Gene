---
allowed-tools: Bash(npx *), Bash(python3 *), Bash(pipeline/. venv/bin/python3 *), Bash(git *)
description: Verify the codebase is in a clean state — typecheck, imports, and pipeline smoke test
---

## Context

- Current branch: !`git branch --show-current`
- Files changed: !`git diff HEAD --stat 2>/dev/null || echo "clean"`

## Your task

Run these checks in order. Report each as ✅ or ❌ with the exact error output for failures.

**1. TypeScript — renderer**
```bash
npx tsc --noEmit -p tsconfig.web.json 2>&1 | head -30
```

**2. TypeScript — main process**
```bash
npx tsc --noEmit -p tsconfig.node.json 2>&1 | head -30
```

**3. Python pipeline — module imports**
```bash
pipeline/.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'pipeline')
from modules import config
from modules import pipeline_orchestrator
from modules import gemini_extractor
from modules import gene_validator
from modules import pubtator_tool
from modules import pubmed_data_collector
from modules import full_text_fetcher
print('All 7 pipeline modules import OK')
" 2>&1
```

**4. Gene validator — HGNC database loads**
```bash
pipeline/.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'pipeline')
from modules.gene_validator import GeneValidator
v = GeneValidator()
result = v.resolve_gene_symbol('BRCA1')
assert result is not None, 'BRCA1 lookup failed'
result2 = v.resolve_gene_symbol('TP53')
assert result2 is not None, 'TP53 lookup failed'
print(f'Gene validator OK — HGNC loaded, BRCA1={result}, TP53={result2}')
" 2>&1
```

**5. Abstract screener — smoke test**
```bash
pipeline/.venv/bin/python3 -c "
import sys; sys.path.insert(0, 'pipeline')
from modules.abstract_screener import has_genetic_content
# Abstract must be >=100 chars to pass the length gate
long_abstract = ('BRCA1 mutation causes increased cancer risk in hereditary breast cancer patients. '
                 'Variant p.Arg175His identified in cohort study of 500 individuals with sequencing.')
ok, score, _ = has_genetic_content(long_abstract, 'BRCA1 variant study')
assert ok, f'Expected pass, got score {score}'
fail, score2, _ = has_genetic_content('Patient satisfaction with nursing care in ICU improved after implementation of the new unit protocols and staffing guidelines across three hospitals.', 'Nursing quality')
assert not fail, f'Expected reject, got score {score2}'
print(f'Abstract screener OK — pass={score}, reject={score2}')
" 2>&1
```

**6. pytest — full test suite (offline, no API keys needed)**
```bash
pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short 2>&1 | tail -20
```

After all checks, give a one-line verdict:
- **All green:** "Codebase verified ✅ — safe to commit/deploy"
- **Any red:** "Verification failed ❌ — do not commit until fixed"

Fix any failures before marking a task complete.
