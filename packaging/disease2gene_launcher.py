#!/usr/bin/env python3
"""Disease2Gene — Standalone app entry point.

Used by PyInstaller to create a bundled .app / .exe.
Sets up paths for frozen (bundled) execution, then runs the Flask server.
"""

import os
import sys
import webbrowser
import threading
import logging


def get_base_path():
    """Get the base path for bundled resources."""
    if getattr(sys, 'frozen', False):
        # Running as a PyInstaller bundle
        return sys._MEIPASS
    else:
        # Running as a script
        return os.path.dirname(os.path.abspath(__file__))


def get_data_dir():
    """Get writable data directory for outputs."""
    if getattr(sys, 'frozen', False):
        # Use ~/Disease2Gene for output data when running as app
        data_dir = os.path.join(os.path.expanduser("~"), "Disease2Gene")
    else:
        data_dir = os.path.join(get_base_path(), "data")
    os.makedirs(os.path.join(data_dir, "output"), exist_ok=True)
    return data_dir


def main():
    base = get_base_path()
    data_dir = get_data_dir()

    # Ensure modules are importable
    sys.path.insert(0, base)

    # Set working directory so relative paths in modules work
    os.chdir(base)

    # Create data/output in writable location
    os.makedirs(os.path.join(data_dir, "output"), exist_ok=True)

    # Point data dir to writable location
    os.environ["DISEASE2GENE_DATA_DIR"] = data_dir

    # Import and configure Flask app
    from gui.app_server import app, PipelineLogHandler

    # Set up logging
    handler = PipelineLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    port = int(os.environ.get("PORT", 8050))
    url = f"http://localhost:{port}"

    # Open browser after a short delay
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    print(f"\n  🧬 Disease2Gene is running at {url}\n")
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
