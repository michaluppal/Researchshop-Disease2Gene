# Pipeline Viewer

Interactive, self-contained HTML view of the ResearchShop extraction pipeline.
Each box is a function or stage; connections show data flow. Click a node for its
schema, config flags, and audit cross-references. Load a trace file to see actual
data that flowed through each stage for one example paper.

## Two modes

1. **Static mode** — open `index.html` directly in a browser (no server). Shows
   the pipeline schema with clickable nodes. Drag a `trace_<pmid>.json` file onto
   the page to populate nodes with real data from a past run.
2. **Live mode** — start `serve.py`, open `http://localhost:8765/`. Type a PMID,
   click **Run pipeline**. Nodes light up in real time as stages complete:
   grey (waiting) → yellow (running) → green (done) → red (failed). Clicking a
   node at any time shows the actual values that flowed through. Figure images
   render inline; click a thumbnail for a full-size modal viewer.

## Quick use — static mode

Open `index.html` in any modern browser. No build step, no server, no
dependencies. Everything is inline.

Without a trace file, the viewer shows the static pipeline schema. Every stage
links to its section in `docs/pipeline-understanding.md` and any related audit
findings in `Final_Audit.md`.

## Quick use — live mode

Start the server:

```bash
python publication/figures/pipeline-viewer/serve.py
```

Open <http://localhost:8765/>, click **⚙ Settings**, paste your Gemini API key
and NCBI Entrez email, click Save. Then enter a PMID (default `34876594`) and
click **Run pipeline**. The viewer:

- Resets all nodes to "waiting" grey, then transitions to yellow/green/red as
  events arrive via Server-Sent Events.
- Streams a live log strip at the bottom with `PROGRESS:`, `LOG:`, and
  tracer events.
- Populates each instrumented node's side panel with real inputs, outputs, and
  figures as they happen.
- Shows PMC figure images inline (loaded directly from NCBI's CDN).
- "View full" buttons appear for long JSON payloads — open a modal with the
  complete content.

One run at a time; a second `/run` request while active returns 409.

### Secrets handling

`GEMINI_API_KEY` and `ENTREZ_EMAIL` can be provided two ways:

- **Via the ⚙ Settings modal in the UI** (recommended) — values are held in
  memory inside `serve.py` only, never written to disk, never echoed back to
  the browser (the UI only sees a boolean "is it set?" flag for the API key).
- **Via env vars before launching** `serve.py` — same effect as Settings; the
  server pre-loads them at startup. The UI still lets you override per-session.

Both values clear when you stop the server. There is no "remember across
restarts" option by design — if you want persistence, keep them in your shell's
env or a `.env` file you source before `serve.py`.

## Generating a trace from the CLI (flight-recorder mode, no server)

Run the pipeline with `--trace-pmid <PMID>` added to the usual CLI:

```bash
python pipeline/run_pipeline.py \
    --query "" \
    --pmids '["34876594"]' \
    --authors '[]' \
    --columns '{"Key Finding":"Main genetic finding","Disease Association":"Associated condition"}' \
    --top-n 1 \
    --output-dir /tmp/rs_trace_demo \
    --trace-pmid 34876594
```

(Remember `GEMINI_API_KEY` and `ENTREZ_EMAIL` must be set in the environment.)

On completion, the output directory will contain:

- `final_enriched_results_*.csv` — the normal pipeline output
- `trace_34876594.json` — **the flight-recorder file**

Drag `trace_34876594.json` onto the viewer (or use the "Load trace.json" button
in the header). Nodes that captured data get a green dot in their top-right
corner. Click any traced node to see the actual inputs and outputs for that
paper.

## How the tracer works

The tracer is **opt-in and zero-cost when off**. The Python pipeline checks one
env var (`TRACE_PMID`) on each `capture()` call; if unset, the call returns
immediately with one dict lookup.

- When `--trace-pmid` is passed, `run_pipeline.py` sets `TRACE_PMID`.
- Each multiprocessing worker checks its own PMID against `TRACE_PMID` and emits
  events only for the matching paper.
- Workers write per-process `.jsonl` partials into `{output_dir}/.trace_partials/`.
- The orchestrator merges partials into the final `trace_{pmid}.json` at the
  end of the run and deletes the partials.
- **Live mode only** — when `TRACE_LIVE_FILE` is also set (by `serve.py`), every
  `capture()` additionally appends a JSON line to that single shared file. The
  server tails it and forwards each line as an SSE event to the browser.

Only one paper can be traced per run. Trace data values go through `summarise()`
which caps string lengths and list sizes — the trace file stays readable.

## Instrumented stages (current)

Already emitting trace events:

- `user_selection` · `pubmed_metadata` · `full_text_fetch` · `text_cleaning`
- `pubtator_ner` · `citation_fetch`
- `abstract_pass` · `fulltext_pass_greedy` · `fulltext_pass_recall`
- `deterministic_scan` · `figure_analysis` · `pubtator_merge` · `candidate_meta`
- `grounding_check` · `hgnc_validation` · `low_confidence_gate` · `corroboration_gate`
- `detail_extraction` · `row_merge` · `evidence_backfill`
- `strict_gate` · `citation_validation` · `evidence_gate`

Not yet instrumented (nodes display schema only, no trace data):

- `abstract_screening` (forensic, pass-through) · `context_validation`
- `ncbi_enrichment` · `topn_policy` · `dedup` · `column_reorder` · `output_writer`

Add more by calling `pipeline_tracer.capture(node_id, pmid=pmid, inputs=..., outputs=...)`
at the appropriate site. Keep node IDs in sync with the `NODES` table in
`index.html`.

## Related docs

- `docs/pipeline-understanding.md` — full narrative trace of the pipeline
- `Final_Audit.md` — findings (F1–F10) the viewer cross-references
- `.claude/rules/memory-pipeline.md` — stage-level reference for Claude sessions
