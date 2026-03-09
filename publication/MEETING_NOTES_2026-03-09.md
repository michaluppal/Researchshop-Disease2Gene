# Meeting Notes: ResearchShop Disease2Gene — Publication Planning

**Date:** 2026-03-09
**Attendees:** Michał Bujniewicz-Uppal, Catherine Suski-Grabowski, Łukasz Górski
**Topic:** SoftwareX Publication + Demo + Task Delegation

---

## 1. Demo Plan

### Installation Demo (5 min)
- **macOS:** DMG installer ready at `dist/researchshop-desktop-1.0.0.dmg` (245 MB)
  - Drag-and-drop install, first-launch auto-creates Python venv
  - Onboarding wizard: research-use disclaimer → API key → output dir → email
- **Windows:** EXE installer not yet built (needs Windows CI or machine)
- **Linux:** AppImage/deb can be built with `npm run package:linux`

### Live Pipeline Run (10 min)
1. Enter a PubMed query (e.g., "BRCA1 breast cancer genomics")
2. Show gene relevance scoring in paper selection modal
3. Start pipeline — watch live progress, stage breakdown, Gemini usage bar
4. Explore results: confidence badges (CORROBORATED/MEDIUM/LOW/REVIEW), citations, metadata columns
5. Export CSV

---

## 2. Architecture Overview (Stable — Won't Change)

### System Layers

```
┌─────────────────────────────────────────────────────┐
│  ELECTRON UI (TypeScript/React)                      │
│  QueryBuilder → TopicResultsModal → Pipeline → Results│
│  Gene relevance scoring runs HERE (pre-submission)   │
├──────────────── IPC Bridge ──────────────────────────┤
│  PROGRESS:{json} | LOG:{json} | RESULT:{json}        │
│  Secrets via env vars (GEMINI_API_KEY, ENTREZ_EMAIL)  │
├─────────────────────────────────────────────────────┤
│  PYTHON PIPELINE (multiprocessing worker pool)       │
│  Stage 3: Full-Text Fetch (PMC/Europe PMC, OA-only)  │
│  Stage 4: PubTator NER (precision floor)             │
│  Stage 5: Gemini LLM Extraction (recall ceiling)     │
│  Stage 6: Gene Validation (HGNC + citation check)    │
│  Stage 7: Orchestration & CSV Output                 │
├─────────────────────────────────────────────────────┤
│  VALIDATION FRAMEWORK                                │
│  HGNC (44,943 local) → Grounding Check → Biotype →  │
│  Variant HGVS → Citation Match → Confidence Gate 0.7 │
└─────────────────────────────────────────────────────┘
```

### Key Design Decisions (Locked)
1. **Hybrid NER+LLM** — PubTator (precision) + Gemini (recall). Neither alone sufficient.
2. **Desktop-first, no server** — privacy-preserving, zero cost, users bring own API key.
3. **OA-only** — no paywall bypass, no Playwright. Legal clarity + reliability.
4. **Grounding check** — every LLM-extracted gene must appear in paper text.
5. **Confidence threshold 0.7** — medical accuracy decision, not performance knob.
6. **Deterministic candidate seeding** — PubTator+HGNC lexicon constrain LLM hallucination.

### External APIs Used
| API | Purpose | Auth Required |
|-----|---------|---------------|
| Google Gemini Flash | LLM extraction | User API key (free tier: 1,500 calls/day) |
| NCBI Entrez | PubMed search + PMC full text | ENTREZ_EMAIL (optional) |
| PubTator3 | NER gene/variant extraction | None |
| HGNC REST | Gene validation (fallback) | None |
| MyGene.info | Gene validation (2nd fallback) | None |
| iCite (NIH) | Citation ranking (primary) | None |
| Semantic Scholar | Citation ranking (fallback) | None |

---

## 3. Codebase Statistics

| Component | Location | Lines of Code |
|-----------|----------|---------------|
| Python pipeline | `python/modules/` | ~7,300 |
| Electron main process | `src/main/` | ~1,000 |
| React renderer | `src/renderer/` | ~8,000 |
| Python tests | `python/tests/` | ~1,200 |
| Benchmark scripts | `python/scripts/` | ~1,600 |
| HGNC database | `python/data/reference/` | 44,943 genes (6.6 MB) |
| Audit log | `AUDIT.md` | ~4,100 lines |
| **Total** | | **~23,200 lines** |

### Key Python Modules
| Module | LOC | Purpose |
|--------|-----|---------|
| `gemini_extractor.py` | 1,703 | Core LLM extraction engine (2-stage + figure analysis) |
| `full_text_fetcher.py` | 1,394 | PMC JATS XML + Europe PMC fallback |
| `gene_validator.py` | 940 | HGNC validation + citation cross-referencing |
| `pipeline_orchestrator.py` | 883 | Multiprocessing coordination + CSV output |
| `pubtator_tool.py` | 575 | PubTator3 NER integration |
| `abstract_screener.py` | 407 | Keyword scoring (now UI-side, retained for benchmarking) |
| `pubmed_data_collector.py` | 395 | PubMed search + iCite/S2 ranking |
| `config.py` | 172 | All feature flags and configuration |

---

## 4. Current Benchmark Results

### Per-Type F1 (Full-LLM Mode, 3 runs each)
| Type | F1 | Hallucinated Genes |
|------|----|--------------------|
| Cancer genomics (4 papers) | 0.668 | 0 |
| GWAS (3 papers) | 0.611 | 0 |
| RNA-seq (2 papers) | 0.600 | 0 |
| Rare disease (2 papers) | 0.167 | 0 |
| Pharmacogenomics (1 paper) | TBD | — |

### Figure Analysis Impact (36-run controlled experiment)
- GBM paper: F1-ON=1.000, F1-OFF=0.167 (ΔF1=+0.833)
- Cancer genomics controls: ΔF1=0
- GWAS control: ΔF1=0
- **Key finding:** Figure analysis improves precision, not recall

### Citation Validation Accuracy
- T2D GWAS (PMID 17463248): 19/20 = 95%
- Miller syndrome (PMID 19915526): 12/18 = 67%

---

## 5. What's Left To Do

### Only 1 Blocking Audit Item
- **[STATS] Inter-rater reliability** (A3 RED #4) — Need 2nd annotator on ≥3 gold-standard papers, compute Cohen's κ. **→ SUSKI**

### Paper Tasks
- [x] Architecture diagram updated (SVG + PDF)
- [x] LaTeX paper rewritten for current architecture (6 pages, compiles)
- [ ] **Review paper accuracy** — verify benchmark numbers, methods description → **ALL**
- [ ] **Biological methods review** — gene validation, variant patterns, biotype filtering → **SUSKI**
- [ ] **AI methodology section expansion** — LLM prompting strategy, hallucination mitigation → **GÓRSKI**
- [ ] **Reproducibility section** — benchmark runner instructions, seed fixing → **GÓRSKI**
- [ ] **Final benchmark run** — re-run 12 papers on current codebase, update numbers
- [ ] **Windows EXE build** — needs Windows machine or CI

### Before Open-Source Release
- [ ] Update GitHub repository URL in metadata
- [ ] Verify README installation instructions on fresh machine
- [ ] Create GitHub Release with DMG + EXE + AppImage

---

## 6. Suggested Task Delegation

### Catherine Suski-Grabowski (Genetics/Omics Expert)

| Task | Priority | Rationale |
|------|----------|-----------|
| **Inter-rater reliability annotation** | 🔴 Blocking | She has the domain expertise to independently annotate gold-standard papers. Need ≥3 papers, then compute Cohen's κ with Michał's annotations. |
| **Gold standard validation** | 🔴 High | Review `gold_standard.json` — are the expected genes correct for each paper? Are any missing? |
| **Biological methods review** | 🟡 Medium | Review paper Section 2.5 (Validation Framework) — is the HGNC validation described accurately? Are the variant patterns complete? |
| **Clinical disambiguation review** | 🟡 Medium | The ESR/AST/CRP clinical-vs-molecular ambiguity is a key limitation. Her molecular genetics expertise can assess whether the current mitigation (prompt clause + corroboration gate) is adequate. |
| **Evaluation dataset expansion** | 🟢 Low | Suggest additional papers for the benchmark, especially rare disease and pharmacogenomics (currently weakest categories). |

### Łukasz Górski (AI/IT Expert)

| Task | Priority | Rationale |
|------|----------|-----------|
| **AI methodology section** | 🔴 High | Expand paper Section 2.2 (Hybrid NER-LLM Architecture) — describe the prompting strategy, deterministic seeding, grounding check, and evidence gate in formal terms. His XAI publications are directly relevant. |
| **Reproducibility & transparency** | 🔴 High | Write a reproducibility section for the paper — benchmark runner instructions, seed fixing, stochasticity quantification. His EU AI Act work on LLM transparency maps directly. |
| **Software architecture description** | 🟡 Medium | Review/expand paper Section 2.1 (System Architecture) — Electron+Python IPC protocol, multiprocessing worker pool, security model. His HPC background helps here. |
| **Windows EXE build** | 🟡 Medium | If he has access to a Windows machine or CI, build the NSIS installer. |
| **Ethical AI framing** | 🟢 Low | Frame the research-use disclaimer and hallucination mitigation in the context of EU AI Act / responsible AI. This could be a unique angle for the paper. |

### Michał Bujniewicz-Uppal (Lead Developer)

| Task | Priority |
|------|----------|
| **Final benchmark run** on current codebase | 🔴 High |
| **Paper revision** incorporating co-author feedback | 🔴 High |
| **Windows EXE build** (CI/CD or manual) | 🟡 Medium |
| **GitHub Release** preparation | 🟡 Medium |
| **AUDIT.md sync** with any final changes | 🟡 Medium |

---

## 7. Publication Plan

### Target: SoftwareX (Elsevier)

**Format:** Original Software Publication
**Typical length:** 6–8 pages (current draft: 6 pages, fits well)
**Review process:** Peer review (2–3 reviewers)
**APC:** Free for open-access (SoftwareX is fully OA)

### Required Deliverables
1. ✅ LaTeX manuscript (`publication/main.tex`, 6 pages, compiles)
2. ✅ Code metadata table (`publication/softwarex_metadata.tex`)
3. ✅ Architecture diagram (`publication/architecture_diagram_en.pdf`)
4. ✅ MIT License
5. ✅ README with installation + usage
6. ⬜ Code archive (GitHub release or Zenodo DOI)
7. ⬜ Inter-rater reliability data
8. ⬜ Reproducibility instructions (benchmark runner)

### Timeline Proposal

| Week | Deliverable | Owner |
|------|-------------|-------|
| Mar 9–15 | Suski: begin inter-rater annotation (≥3 papers) | CS |
| Mar 9–15 | Górski: review AI methodology section, propose edits | ŁG |
| Mar 9–15 | Michał: final benchmark run, Windows build | MB |
| Mar 16–22 | Incorporate co-author feedback, expand paper | ALL |
| Mar 23–29 | Final revision, create GitHub Release + Zenodo DOI | MB |
| Mar 30+ | Submit to SoftwareX | ALL |

---

## 8. Known Problems & Solutions Pipeline

### Active Challenges
| Problem | Impact | Current Mitigation | Next Steps |
|---------|--------|-------------------|------------|
| LLM stochasticity (different genes per run) | Reproducibility | Multi-run averaging | Quantify in paper |
| Clinical-vs-molecular ambiguity (ESR/AST/CRP) | False positives | Prompt clause + corroboration gate | Benchmark with more clinical papers |
| OA-only (~40% papers paywalled) | Limited recall | 4× overfetch factor | Document as limitation |
| Rare disease F1=0.167 | Benchmark weakness | One paper was paywalled | Add more rare disease papers |
| Citation stochasticity (0–100% per run) | Metric unreliability | Multi-run averaging | Report as known limitation |

### Resolved Challenges (Summary of 33 Post-FDA Audit Items)
- ✅ OS keychain encryption (replaced hardcoded key)
- ✅ Path traversal validation in IPC
- ✅ Research-use disclaimer in onboarding
- ✅ CORROBORATED confidence badge (renamed from HIGH)
- ✅ Biotype filtering (protein-coding default)
- ✅ Context window hard gate (80% threshold)
- ✅ Figure caption grounding check
- ✅ Wilson CIs on benchmark metrics
- ✅ Content Security Policy headers
- ✅ Renderer sandbox enabled
- ✅ PMID input sanitisation
- ... and 22 more (all documented in AUDIT.md)

---

## 9. Existing Paper Status

The LaTeX paper has been **completely rewritten** to reflect the current architecture. Major changes from previous draft:

| Aspect | Old (previous draft) | New (current) |
|--------|---------------------|---------------|
| UI Framework | CustomTkinter (Python) | Electron + React (TypeScript) |
| Full-text fetch | Trafilatura + Playwright | PMC JATS XML + Europe PMC (OA-only) |
| Citation ranking | Semantic Scholar primary | iCite primary, S2 fallback |
| NER integration | None | PubTator3 hybrid architecture |
| Validation | Basic HGNC + regex | Multi-layer: HGNC + grounding + biotype + citation cross-ref |
| Benchmark | 19 MIS-C papers (single run) | 12 papers × 5 types × 3 runs + 36-run figure experiment |
| Deployment | Flask/Docker | Desktop installer (DMG/EXE/AppImage) |
| Security | Not addressed | OS keychain, CSP, sandbox, path validation |

### What the Paper Covers (6 pages)
1. **Motivation** — knowledge bottleneck, VUS, LLM hallucinations
2. **Architecture** — 7-stage pipeline, hybrid NER-LLM, IPC protocol
3. **Schema-driven extraction** — user-defined columns
4. **Desktop application** — installer, onboarding, security
5. **Validation framework** — 4 levels (HGNC, grounding, HGVS, citation)
6. **Benchmark results** — F1 per type, figure analysis, PubTator comparison
7. **Impact** — applications, cost analysis, limitations
8. **Conclusions** — future work

### What Still Needs Work in the Paper
- Benchmark numbers need verification against latest run
- AI methodology section could be expanded (Górski)
- Inter-rater reliability section needed (Suski)
- Reproducibility instructions section (Górski)
- Figure 1 (architecture diagram) might benefit from simplification for print
