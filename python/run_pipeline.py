#!/usr/bin/env python3
"""Entry point for Electron desktop app to run the research pipeline."""
import argparse
import json
import sys
import os

# Add modules to path
sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(description='ResearchShop Pipeline')
    parser.add_argument('--query', type=str, default='')
    parser.add_argument('--pmids', type=str, default='[]', help='JSON array of PMIDs')
    parser.add_argument('--authors', type=str, default='[]', help='JSON array of author names')
    parser.add_argument('--columns', type=str, default='{}', help='JSON object of column name->description')
    parser.add_argument('--top-n', type=int, default=10)
    parser.add_argument('--output-dir', type=str, required=True)
    args = parser.parse_args()

    # Secrets are passed via environment variables, never CLI args (visible in ps aux).
    # GEMINI_API_KEY and ENTREZ_EMAIL must be set in the process environment by the caller.
    gemini_api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    entrez_email = os.environ.get('ENTREZ_EMAIL', '').strip()

    if not gemini_api_key:
        print('RESULT:' + json.dumps({'error': 'GEMINI_API_KEY environment variable is not set'}), flush=True)
        sys.exit(1)
    if not entrez_email:
        print('RESULT:' + json.dumps({'error': 'ENTREZ_EMAIL environment variable is not set'}), flush=True)
        sys.exit(1)

    from modules import config
    config.GEMINI_API_KEY = gemini_api_key
    config.ENTREZ_EMAIL = entrez_email
    config.OUTPUT_DIR = args.output_dir
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    from modules.pipeline_orchestrator import run_complete_pipeline

    pmids = json.loads(args.pmids)
    authors = json.loads(args.authors)
    columns = json.loads(args.columns)

    def progress_callback(stage, pct, stats):
        msg = json.dumps({"stage": stage, "percent": pct, "stats": stats})
        print(f"PROGRESS:{msg}", flush=True)

    def log_callback(level, msg, detail=None):
        payload = json.dumps({"level": level, "msg": msg, "detail": detail})
        print(f"LOG:{payload}", flush=True)

    try:
        result = run_complete_pipeline(
            query=args.query,
            specific_pmids=pmids,
            specific_authors=authors,
            user_columns=columns,
            top_n_cited=args.top_n,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
        if result:
            print(f"RESULT:{json.dumps(result)}", flush=True)
        else:
            print(f"RESULT:{json.dumps({'error': 'No results produced'})}", flush=True)
    except Exception as e:
        print(f"RESULT:{json.dumps({'error': str(e)})}", flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
