
import os
import asyncio
import json
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from execution.playwright_automation import ZohoExpenseAutomation
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

    with open("settings.json", "r") as f:
        settings = json.load(f)

    logger.info(f"{settings['org_name']} Expense Automation | Date: {run_date}")

    headless = "--visible" not in sys.argv
    bot = ZohoExpenseAutomation(headless=headless)
    cleaner = DataCleaner()
    uploader = PostgresUploader()

    # 1. Download
    file_path = await bot.run(run_date)
    
    if file_path:
        # 2. Clean
        df = cleaner.process_expenses(file_path)
        
        # 3. Upload
        if not df.empty:
            # For Expenses, we use a composite key of Month, Category and Amount for targeted upsert
            # We need to ensure the uploader uses these keys
            success = uploader.upload(df, settings['table'], ["Month", "Category", "Amount"])
            if success:
                logger.info(f"Successfully synced {settings['name']} to {settings['table']}")
            else:
                logger.error(f"Failed to upload to {settings['table']}")
        else:
            logger.warning("No records found in expense report.")
    else:
        logger.error("Automation failed to download report.")

if __name__ == "__main__":
    asyncio.run(main())
