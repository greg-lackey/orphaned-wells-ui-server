"""
run_synthesis.py — Standalone CLI to run Layer 2 synthesis independently.

Usage:
    python -m pg_sync.run_synthesis
    python -m pg_sync.run_synthesis --schema isgs
    python -m pg_sync.run_synthesis --log-level DEBUG
"""
import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate Layer 2 well-state tables from Layer 1 completion_reports."
    )
    parser.add_argument(
        "--schema",
        default="isgs",
        help="PostgreSQL schema to read from and write to (default: isgs).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    import psycopg2
    from . import config
    from .synthesizer import run_synthesis

    conn = psycopg2.connect(config.PG_DSN)
    conn.autocommit = False
    try:
        run_synthesis(conn, schema=args.schema)
    except Exception as exc:
        logging.critical("Synthesis failed: %s", exc, exc_info=True)
        conn.close()
        sys.exit(1)

    conn.close()
    print("Layer 2 synthesis complete.")


if __name__ == "__main__":
    main()
