"""
Database Checker Script.

Queries the PostgreSQL database to identify missing dates in the Petpooja reports.
"""

import os
import datetime
import sys
from sqlalchemy import text

# Add current directory to path to allow running from root
sys.path.append(os.getcwd())

from execution.pgsql_uploader import PostgresUploader
from execution.logger_helper import LoggerHelper

def get_missing_dates(start_date: datetime.date, end_date: datetime.date):
    """Checks the database for missing dates in the specified range."""
    uploader = PostgresUploader()
    logger = LoggerHelper().logger

    query = text(f'SELECT DISTINCT date::date FROM "{uploader.db_schema}"."{uploader.db_table}" WHERE date::date BETWEEN :start AND :end ORDER BY date::date ASC')
    
    try:
        with uploader.engine.connect() as conn:
            result = conn.execute(query, {"start": start_date, "end": end_date})
            existing_dates = {row[0] for row in result}
            
            all_dates = {start_date + datetime.timedelta(days=i) for i in range((end_date - start_date).days + 1)}
            missing_dates = sorted(list(all_dates - existing_dates))
            
            logger.info(f"Existing dates in range {start_date} to {end_date}: {len(existing_dates)}")
            logger.info(f"Missing dates in range {start_date} to {end_date}: {len(missing_dates)}")
            
            return missing_dates
    except Exception as e:
        logger.error(f"Error checking database: {e}")
        return []

if __name__ == "__main__":
    # Check for the last 30 days
    end_date = datetime.date.today() - datetime.timedelta(days=1)
    start_date = end_date - datetime.timedelta(days=30)
    
    missing = get_missing_dates(start_date, end_date)
    if missing:
        print(f"Missing dates: {missing}")
    else:
        print("No missing dates in the last 30 days.")
