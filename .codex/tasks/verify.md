# Verify Recipe

Use this before committing pipeline or Electron integration changes. Report each check as pass/fail and include exact failure output when something breaks.

## Context

- Current branch: `git branch --show-current`
- Changed files: `git diff HEAD --stat`

## Checks

1. Renderer typecheck:
   `npx tsc --noEmit -p config/tsconfig.web.json`

2. Main-process typecheck:
   `npx tsc --noEmit -p config/tsconfig.node.json`

3. Python pipeline imports:
   `pipeline/.venv/bin/python3 -c "import sys; sys.path.insert(0, 'pipeline'); from modules import config, pipeline_orchestrator, gemini_extractor, gene_validator, pubtator_tool, pubmed_data_collector, full_text_fetcher; print('All 7 pipeline modules import OK')"`

4. Gene validator smoke test:
   `pipeline/.venv/bin/python3 -c "import sys; sys.path.insert(0, 'pipeline'); from modules.gene_validator import GeneValidator; v=GeneValidator(); assert v.resolve_gene_symbol('BRCA1') is not None; assert v.resolve_gene_symbol('TP53') is not None; print('Gene validator OK')"`

5. Abstract screener smoke test:
   `pipeline/.venv/bin/python3 -c "import sys; sys.path.insert(0, 'pipeline'); from modules.abstract_screener import has_genetic_content; ok, score, _ = has_genetic_content('BRCA1 mutation causes increased cancer risk in hereditary breast cancer patients. Variant p.Arg175His identified in cohort study of 500 individuals with sequencing.', 'BRCA1 variant study'); assert ok, score; fail, score2, _ = has_genetic_content('Patient satisfaction with nursing care in ICU improved after implementation of the new unit protocols and staffing guidelines across three hospitals.', 'Nursing quality'); assert not fail, score2; print('Abstract screener OK')"`

6. Offline Python tests:
   `pipeline/.venv/bin/python3 -m pytest pipeline/tests/ -v --tb=short`

End with one verdict:

- All green: `Codebase verified - safe to commit/deploy`
- Any red: `Verification failed - do not commit until fixed`
