#!/usr/bin/env python3
"""Wrapper to run Disease2Gene pipeline from Electron.

Reads JSON config from stdin, runs the pipeline, and outputs
progress/result/error as JSON lines to stdout.
"""

import sys
import json
import os
import logging
import traceback

# Add project root to path so we can import modules.*
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)


def main():
    # Read config from stdin
    try:
        raw = sys.stdin.read()
        config = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        print(json.dumps({"type": "error", "message": f"Failed to parse config: {e}"}), flush=True)
        sys.exit(1)

    # Set environment variables from config
    os.environ['GEMINI_API_KEY'] = config.get('geminiApiKey', '')
    os.environ['ENTREZ_EMAIL'] = config.get('entrezEmail', '')

    if config.get('entrezApiKey'):
        os.environ['ENTREZ_API_KEY'] = config['entrezApiKey']
    if config.get('outputDir'):
        os.environ['OUTPUT_DIR'] = config['outputDir']

    # Configure logging to stderr so it doesn't interfere with JSON output on stdout
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s",
        stream=sys.stderr,
    )

    # Progress callback that outputs JSON lines to stdout
    def progress_callback(stage, pct):
        msg = {"type": "progress", "stage": stage, "pct": pct}
        print(json.dumps(msg), flush=True)

    try:
        from modules.pipeline_orchestrator import run_complete_pipeline

        # Build user_columns dict from the config
        user_columns = config.get('userColumns', {})
        if isinstance(user_columns, list):
            # Convert [{name, description}, ...] to {name: description, ...}
            user_columns = {col['name']: col['description'] for col in user_columns if 'name' in col}

        result = run_complete_pipeline(
            query=config.get('query', ''),
            specific_pmids=config.get('pmids', []),
            specific_authors=config.get('authors', []),
            user_columns=user_columns,
            top_n_cited=config.get('topNCited', 20),
            max_results=config.get('maxResults'),
            progress_callback=progress_callback,
        )

        if result:
            print(json.dumps({"type": "result", "data": result}, default=str), flush=True)
        else:
            print(json.dumps({"type": "error", "message": "Pipeline returned no results"}), flush=True)

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"Pipeline failed: {e}\n{tb}")
        print(json.dumps({"type": "error", "message": str(e)}), flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
