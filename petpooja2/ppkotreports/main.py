"""
Central Application Entry Point.

Orchestrates the Petpooja to PostgreSQL automation pipeline using a
strictly headless Playwright architecture:
    1. Extraction: Launches persistent Playwright headless Firefox (reusing session from /home/mcsuser/work/rwppdatatransfer/playwrightprofile/).
    2. Cleaning: Processes the downloaded CSV.
    3. Database: Upserts records into PostgreSQL.

Date Resolution Strategy
------------------------
- When NO date arguments are supplied, the pipeline automatically targets
  **yesterday in India Standard Time (IST / Asia/Kolkata, UTC+5:30)**.
  This is timezone-safe: even when running on a UTC AWS Lightsail server,
  the correct IST calendar date is derived.
- When --start / --end are supplied, the pipeline runs for every date in
  that inclusive range (useful for backfilling).
- When a single positional date (YYYY-MM-DD) is supplied, it is used
  directly without any timezone calculation.
"""

import os
import sys
import asyncio
import datetime
import argparse
import traceback
from zoneinfo import ZoneInfo  # stdlib since Python 3.9

import pandas as pd

from execution.playwright_automation import PlaywrightAutomation
from execution.data_cleaner import DataCleaner
from execution.pgsql_uploader import PostgresUploader
from execution.logger_helper import LoggerHelper

# India Standard Time — used for all "today / yesterday" calculations so that
# the program works correctly on UTC-based servers (e.g., AWS Lightsail Debian).
_IST = ZoneInfo("Asia/Kolkata")


def _today_ist() -> datetime.date:
    """Return today's date in Indian Standard Time (IST, UTC+5:30).

    Using IST ensures the correct calendar date is resolved even when the
    host machine (e.g., an AWS Lightsail Debian instance) runs on UTC.

    Returns:
        datetime.date: Today's date as observed in the IST timezone.
    """
    return datetime.datetime.now(tz=_IST).date()


async def run_pipeline(target_date: datetime.date | None = None, headless: bool = True) -> bool:
    """Execute the automation pipeline for a single date.

    Args:
        target_date: The specific date for which to fetch and upload Petpooja
            data. If ``None``, defaults to **today in IST**.

    Returns:
        bool: ``True`` if the full pipeline (download → clean → upload)
            completed without errors, ``False`` otherwise.
    """
    logger_helper = LoggerHelper()
    logger = logger_helper.logger

    success = False
    downloaded_csv = None

    if target_date is None:
        # Stock Summary updates daily at 11:30 PM. 
        # Requirement: Record current date if downloaded today.
        target_date = _today_ist()
        logger.info(
            f"No date supplied — resolved to today in IST: {target_date}"
        )

    logger.info(f"--- Starting Pipeline for {target_date} ---")

    # Ensure a clean workspace by purging any stale files in downloads
    cleaner = DataCleaner()
    cleaner.clear_download_dir()

    try:
        # ==========================================
        # 1. Report Extraction: Playwright Headless
        # ==========================================
        logger.info(f"Initiating Playwright {'Headless' if headless else 'Visible'} extraction...")
        pw_bot = PlaywrightAutomation(headless=headless)
        downloaded_csv = await pw_bot.run(target_date)
        
        if downloaded_csv:
            logger.info("Playwright extraction completed successfully.")
        else:
            logger.error("Playwright failed to download the report.")
            raise RuntimeError("Report download failed.")

        # ==========================================
        # 3. Data Cleaning & Aggregation
        # ==========================================
        logger.info("Starting Data Cleaning and Multi-Outlet Aggregation...")
        cleaner = DataCleaner()
        cleaned_xlsx = cleaner.merge_all_reports(report_date=target_date)
        
        if not cleaned_xlsx:
            raise RuntimeError("Data cleaning and aggregation failed.")
        
        logger.info(f"Consolidated master report finished: {cleaned_xlsx.name}")

        # ==========================================
        # 4. PostgreSQL Upload
        # ==========================================
        logger.info("Starting PostgreSQL upload process...")
        pgsql_uploader = PostgresUploader()
        if pgsql_uploader.upload_to_postgres(cleaned_xlsx):
            logger.info("PostgreSQL upload success.")
            success = True
        else:
            raise RuntimeError("PostgreSQL upload process failed.")

    except Exception as e:
        logger.error(f"Pipeline crashed: {str(e)}")
        logger.error(traceback.format_exc())
        success = False

    finally:
        if success:
            logger.info("--- Pipeline Completed Successfully ---")
        else:
            logger.error("--- Pipeline Failed ---")
            
        return success


def main() -> None:
    """CLI entry point.

    Supports three invocation modes:

    1. **No arguments** — runs for yesterday in IST (timezone-safe default)::

           python main.py

    2. **Single positional date** — runs for that exact date::

           python main.py 2026-02-28

    3. **Date range** — runs for every date in [start, end] inclusive
       (useful for backfilling)::

           python main.py --start 2026-02-01 --end 2026-02-28

    Handles Windows ProactorEventLoop requirement for Playwright.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Petpooja → PostgreSQL pipeline",
    )
    parser.add_argument(
        "date",
        nargs="?",
        metavar="YYYY-MM-DD",
        help="Single target date (optional). Defaults to yesterday in IST.",
    )
    parser.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="Start of a date range (inclusive). Must be paired with --end.",
    )
    parser.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="End of a date range (inclusive). Must be paired with --start.",
    )
    parser.add_argument(
        "--visible",
        action="store_false",
        dest="headless",
        default=True,
        help="Run the browser in visible mode (default: headless).",
    )
    args = parser.parse_args()

    # ── Resolve the list of dates to process ─────────────────────────────────
    dates_to_run: list[datetime.date] = []

    if args.start or args.end:
        # Range mode — both flags are required together
        if not (args.start and args.end):
            parser.error("Both --start and --end must be supplied together.")
        try:
            start_date = datetime.date.fromisoformat(args.start)
            end_date = datetime.date.fromisoformat(args.end)
        except ValueError as exc:
            parser.error(f"Invalid date format: {exc}")
        if start_date > end_date:
            parser.error("--start must be on or before --end.")
        # Build inclusive date list
        delta = (end_date - start_date).days
        dates_to_run = [
            start_date + datetime.timedelta(days=i) for i in range(delta + 1)
        ]
    elif args.date:
        # Single explicit date
        try:
            dates_to_run = [datetime.date.fromisoformat(args.date)]
        except ValueError:
            parser.error(
                f"Invalid date '{args.date}'. Expected format: YYYY-MM-DD."
            )
    else:
        # Default: today in IST (timezone-safe for UTC servers)
        dates_to_run = [_today_ist()]
        print(
            f"No date supplied — defaulting to today in IST: {dates_to_run[0]}"
        )

    # ── Event loop setup (Windows Playwright requirement) ────────────────────
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # ── Run the pipeline for each date ───────────────────────────────────────
    overall_success = True
    try:
        for run_date in dates_to_run:
            print(f"\n>>> Running pipeline for {run_date} (Headless={args.headless}) ...")
            success = asyncio.run(run_pipeline(run_date, headless=args.headless))
            if not success:
                overall_success = False
                print(f"!!! Pipeline FAILED for {run_date}")
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
        sys.exit(130)

    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
