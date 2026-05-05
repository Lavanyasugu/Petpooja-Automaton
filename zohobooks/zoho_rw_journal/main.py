
import os
import asyncio
import json
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from execution.playwright_automation import ZohoJournalAutomation
from execution.data_cleaner import DataCleaner
from execution.pgsql_uploader import PostgresUploader
from execution.logger_helper import LoggerHelper

async def main():
    load_dotenv()
    logger = LoggerHelper().logger
    
    # Handle Date Argument
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        run_date = sys.argv[1] 
    else:
        run_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info(f"Pink Adrak Journal Automation | Date: {run_date}")
    
    with open("settings.json", "r") as f:
        settings = json.load(f)

    headless = "--visible" not in sys.argv
    bot = ZohoJournalAutomation(headless=headless)
    cleaner = DataCleaner()
    uploader = PostgresUploader()

    # 1. Download
    file_path = await bot.run(run_date)
    
    if file_path:
        # 2. Clean
        df = cleaner.process_journals(file_path)
        
        # 3. Upload
        if not df.empty:
            # For Journals, we use a different key logic if available, or just append
            # Adjusting keys to match standard Journal columns
            success = uploader.upload(df, settings['table'], ["Journal Number"])
            if success:
                logger.info(f"Successfully synced {settings['name']} to {settings['table']}")
            else:
                logger.error(f"Failed to upload to {settings['table']}")
        else:
            logger.warning("No records found in journal report.")
    else:
        logger.error("Automation failed to download report.")

if __name__ == "__main__":
    asyncio.run(main())
