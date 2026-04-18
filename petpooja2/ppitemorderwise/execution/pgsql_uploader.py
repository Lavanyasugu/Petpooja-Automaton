"""
PostgreSQL Uploader Module for Itemwise Petpooja Orders.

This module handles the insertion of cleaned sales data into the Amazon Lightsail
PostgreSQL database.
"""

import os
import json
import logging
import pandas as pd
from typing import Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
from execution.logger_helper import LoggerHelper

load_dotenv()

class PostgresUploader:
    """Handles database connections and data insertion for itemwise reports."""

    def __init__(self, settings_path: str = "settings.json"):
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger
        
        # Load settings
        self.settings = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                self.settings = json.load(f)
        
        self.db_host = os.getenv("DB_HOST", self.settings.get("db_host"))
        self.db_port = os.getenv("DB_PORT", self.settings.get("db_port", "5432"))
        self.db_name = os.getenv("DB_NAME", self.settings.get("db_name"))
        self.db_user = os.getenv("DB_USER", self.settings.get("db_user"))
        self.db_pass = os.getenv("DB_PASS", self.settings.get("db_pass"))
        self.db_schema = os.getenv("DB_SCHEMA", self.settings.get("db_schema", "Petpooja"))
        self.db_table = os.getenv("DB_TABLE", self.settings.get("db_table", "order_summary_itemwise"))

        self.conn_str = f"postgresql+psycopg2://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        self.engine = create_engine(self.conn_str)

    def insert_dataframe(self, df: pd.DataFrame, table_name: Optional[str] = None, schema: Optional[str] = None) -> bool:
        table_name = table_name or self.db_table
        schema = schema or self.db_schema
        
        if df.empty:
            self.logger.info("No records to insert.")
            return True

        df = df.copy()

        # Fix Invoice_No Type
        if 'invoice_no' in df.columns:
             df['invoice_no'] = df['invoice_no'].astype(str)

        self.logger.info(f"Preparing to insert {len(df)} records into {schema}.{table_name}...")

        try:
            with self.engine.begin() as conn:
                # 1. Create a temporary table
                df.to_sql("temp_itemwise", conn, if_exists="replace", index=False)
                
                # 2. Build quoted column names for safe SQL execution
                target_cols = [f'"{col}"' for col in df.columns]
                
                select_cols = []
                for col in df.columns:
                    if col.lower() == 'date':
                        select_cols.append(f'CAST("{col}" AS TIMESTAMP)')
                    else:
                        select_cols.append(f'"{col}"')

                cols_str = ", ".join(target_cols)
                select_str = ", ".join(select_cols)
                
                # 3. Perform UPSERT via DELETE + INSERT.
                # Composite Key: invoice_no + item_name + item_total + date
                # We use these to identify unique rows in the itemwise report.
                delete_query = f"""
                    DELETE FROM "{schema}"."{table_name}"
                    WHERE ("invoice_no", "item_name", "item_total", "date") IN (
                        SELECT "invoice_no", "item_name", "item_total", CAST("date" AS TIMESTAMP) 
                        FROM temp_itemwise
                    );
                """
                insert_query = f"""
                    INSERT INTO "{schema}"."{table_name}" ({cols_str})
                    SELECT {select_str} FROM temp_itemwise;
                """

                conn.execute(text(delete_query))
                conn.execute(text(insert_query))
                conn.execute(text("DROP TABLE temp_itemwise;"))
                
                self.logger.info(f"Successfully upserted {len(df)} records into {schema}.{table_name}.")
                return True

        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy Error during insertion: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during database insertion: {e}")
            return False

if __name__ == "__main__":
    print("Testing PostgresUploader initialization...")
    try:
        uploader = PostgresUploader()
        print("Success.")
    except Exception as e:
        print(f"Failed: {e}")
