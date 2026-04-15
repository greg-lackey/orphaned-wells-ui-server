"""
run_sync.py — CLI entry point for the pg_sync ETL pipeline.

Usage:
    python -m pg_sync.run_sync --form completion_reports
    python -m pg_sync.run_sync --form completion_reports --collaborator isgs
    python -m pg_sync.run_sync --form completion_reports --full-sync
    python -m pg_sync.run_sync --form completion_reports --full-sync --log-level DEBUG

Cron example (nightly at 2am):
    0 2 * * * cd /path/to/orphaned-wells-ui-server-pg && \\
        python -m pg_sync.run_sync --form completion_reports >> /var/log/ogrre_pg_sync.log 2>&1
"""
import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync OGRRE reviewed records from MongoDB to PostgreSQL."
    )
    parser.add_argument(
        "--form",
        required=True,
        help="Form type to sync, e.g. completion_reports, plugging_reports",
    )
    parser.add_argument(
        "--collaborator",
        default=None,
        help="Institution key, e.g. isgs, calgem, osage. Defaults to COLLABORATOR env var.",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Ignore last sync timestamp and re-sync all reviewed records.",
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

    from .sync import run_sync  # import here so logging is configured first

    try:
        synced, failed = run_sync(
            form_type=args.form,
            collaborator=args.collaborator,
            full_sync=args.full_sync,
        )
    except Exception as exc:
        logging.critical("Sync failed with unhandled exception: %s", exc, exc_info=True)
        sys.exit(1)

    if failed > 0:
        logging.warning("Sync finished with %d failures.", failed)
        sys.exit(1)

    print(f"Sync complete: {synced} records synced, {failed} failed.")


if __name__ == "__main__":
    main()
