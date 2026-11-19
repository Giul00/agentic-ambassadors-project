"""python -m delivery_crew.api [--port 8000] [--runs-dir runs]"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="API del panel de Delivery Crew")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs-dir", default=None)
    args = parser.parse_args()

    if args.runs_dir:
        os.environ["DELIVERY_CREW_RUNS_DIR"] = args.runs_dir

    import uvicorn

    uvicorn.run("delivery_crew.api.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
