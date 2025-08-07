"""
Electron server entry point.

Starts the Flask app configured for Electron using Waitress.
Detects/sets Electron environment variables and supports basic CLI args.
"""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start TypeComplex Flask server for Electron")
    parser.add_argument("--host", default=os.environ.get("TYPECOMPLEX_HOST", "127.0.0.1"), help="Host interface to bind")
    parser.add_argument("--port", type=int, default=int(os.environ.get("TYPECOMPLEX_PORT", "5001")), help="Port to listen on")
    parser.add_argument("--workers", type=int, default=int(os.environ.get("TYPECOMPLEX_WORKERS", "1")), help="Number of Waitress threads")
    parser.add_argument("--app-path", default=os.environ.get("ELECTRON_APP_PATH", None), help="Base path for app data (uploads, cache, db)")
    return parser.parse_args()


def ensure_env(app_path: str | None) -> None:
    # Signal Electron mode to the Flask app
    os.environ.setdefault("ELECTRON_RUN_AS_NODE", "1")

    # Provide base path for local file storage and DB
    if app_path:
        os.environ["ELECTRON_APP_PATH"] = app_path
    else:
        # Default to repo root (directory containing this file)
        repo_root = os.path.dirname(os.path.abspath(__file__))
        os.environ.setdefault("ELECTRON_APP_PATH", repo_root)

    # Conservative defaults for Flask
    os.environ.setdefault("FLASK_ENV", "development")
    os.environ.setdefault("FLASK_DEBUG", "false")


def main() -> int:
    args = parse_args()
    ensure_env(args.app_path)

    # Import after env is prepared so the correct app variant is loaded
    try:
        from waitress import serve
    except Exception as exc:
        print(f"ERROR: Waitress is required to run the Electron server: {exc}", file=sys.stderr)
        return 1

    try:
        # Import the Electron-configured Flask app
        from app.__init___electron import app  # type: ignore
    except Exception as exc:
        print(f"ERROR: Failed to import Electron Flask app: {exc}", file=sys.stderr)
        return 1

    print(f"Starting TypeComplex (Electron) on http://{args.host}:{args.port} with {args.workers} threads", file=sys.stderr)

    # Start the server
    serve(app, host=args.host, port=args.port, threads=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


