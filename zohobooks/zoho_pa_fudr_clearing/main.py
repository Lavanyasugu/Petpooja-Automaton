
import os
import asyncio
import json
import sys
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from execution.playwright_automation import ZohoReportAutomation
from execution.data_cleaner import DataCleaner
from execution.pgsql_uploader import PostgresUploader
from execution.logger_helper import LoggerHelper

async def main():
    load_dotenv()
    logger = LoggerHelper().logger
    
    # Calculate Date Range: Previous month 1st to Current month 5th
    today = datetime.now()
    
    # From Date: 1st of previous month
    from_date_dt = (today - relativedelta(months=1)).replace(day=1)
    from_date = from_date_dt.strftime("%Y-%m-%d")
    
    # To Date: 5th of current month
    to_date_dt = today.replace(day=5)
    to_date = to_date_dt.strftime("%Y-%m-%d")

    with open("settings.json", "r") as f:
        settings = json.load(f)

    logger.info(f"{settings['org_name']} Fudr Clearing Automation | Range: {from_date} to {to_date}")

    headless = "--visible" not in sys.argv
    bot = ZohoReportAutomation(headless=headless)
    cleaner = DataCleaner()
    uploader = PostgresUploader()

    # 1. Download
    file_path = await bot.run(from_date, to_date, settings['account_name'])
    
    if file_path:
        # Move file to a more specific name if needed, or bot already handles it
        # Actually, bot.run uses from_date/to_date in filename. 
        # I'll update bot.run filename logic inside playwright_automation.py if needed.
        # 2. Clean
        # Note: DataCleaner implementation will need to handle this specific report format
        df = cleaner.process_clearing_account(file_path, from_date, to_date)
        
        # 3. Upload
        if not df.empty:
            # We need to decide on unique columns for this table. 
            # Date, Transaction Details, Amount, etc.
            success = uploader.upload(df, settings['table'], ["Month", "description", "Amount"])
            if success:
                logger.info(f"Successfully synced {settings['name']} to {settings['table']}")
            else:
                logger.error(f"Failed to upload to {settings['table']}")
        else:
            logger.warning("No records found in report.")
    else:
        logger.error("Automation failed to download report.")

if __name__ == "__main__":
    asyncio.run(main())
