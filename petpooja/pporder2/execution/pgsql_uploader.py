"""
PostgreSQL Uploader Module for Petpooja Orders.

This module handles the insertion of cleaned sales data into the Amazon Lightsail
PostgreSQL database under the zohoanalytics schema.
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
    """Handles database connections and data insertion for Petpooja orders."""

    def __init__(self, settings_path: str = "settings.json"):
        """Initialize with database credentials from environment or settings."""
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger
        
        # Load settings
        self.settings = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                self.settings = json.load(f)
        
        # Database parameters: Prioritize settings.json for project-specific isolation
        self.db_host = os.getenv("DB_HOST", self.settings.get("db_host"))
        self.db_port = os.getenv("DB_PORT", self.settings.get("db_port", "5432"))
        self.db_name = os.getenv("DB_NAME", self.settings.get("db_name"))
        self.db_user = os.getenv("DB_USER", self.settings.get("db_user"))
        self.db_pass = os.getenv("DB_PASS", self.settings.get("db_pass"))
        
        # Strictly use settings.json for table/schema to avoid environment variable pollution
        self.db_schema = self.settings.get("db_schema", os.getenv("DB_SCHEMA", "Petpooja"))
        self.db_table = self.settings.get("db_table", os.getenv("DB_TABLE", "pp_waste"))

        missing_vars = []
        for var_name, var_value in [
            ("DB_HOST", self.db_host),
            ("DB_NAME", self.db_name),
            ("DB_USER", self.db_user),
            ("DB_PASS", self.db_pass),
        ]:
            if not var_value:
                missing_vars.append(var_name)

        if missing_vars:
            err_msg = f"Missing required database environment variables: {', '.join(missing_vars)}"
            self.logger.error(err_msg)
            raise ValueError(err_msg)
        
        # Connection string with SSL mode required as per documentation
        self.conn_str = f"postgresql+psycopg2://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        
        try:
            self.engine = create_engine(self.conn_str)
            self.logger.info("Database engine initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize database engine: {e}")
            raise

    def insert_dataframe(self, df: pd.DataFrame, table_name: Optional[str] = None, schema: Optional[str] = None) -> bool:
        """
        Inserts a pandas DataFrame into the specified PostgreSQL table.
        Uses an 'upsert' pattern (on conflict do update) based on invoice_no.
        """
        table_name = table_name or self.db_table
        schema = schema or self.db_schema
        
        if df.empty:
            self.logger.info("No records to insert (DataFrame is empty).")
            return True

        # --- Sanitization & Type Conversion (Section 4.3 of pgsql.md) ---
        # Note: We NO LONGER lowercase column names here because the DB table pp_orders
        # uses CamelCase headers (e.g., Invoice_No) which require double-quoting.
        # Mapping should happen in the DataCleaner to ensure columns match DB exactly.
        df = df.copy()

        # Fix Date Type: Ensure it's a date object to help SQL inference
        # The DB column is named "Date".
        if 'Date' in df.columns:
            try:
                df['Date'] = pd.to_datetime(df['Date']).dt.date
            except Exception as e:
                self.logger.warning(f"Note: Date conversion issue: {e}")
        elif 'date' in df.columns:
             # Fallback for lowercase 'date' if not already cleaned
             try:
                df['date'] = pd.to_datetime(df['date']).dt.date
             except Exception:
                 pass

        # Fix Invoice_No Type: P_orders.Invoice_No is TEXT
        # Ensure it's treated as string to avoid operator mismatch errors.
        for col in ["Invoice No", "Invoice_No", "invoice_no"]:
            if col in df.columns:
                df[col] = df[col].astype(str)

        self.logger.info(f"Preparing to insert {len(df)} records into {schema}.{table_name}...")

        try:
            with self.engine.begin() as conn:
                # Ensure schema exists
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}";'))
                
                # 1. Create a temporary table
                df.head(0).to_sql("temp_orders", conn, if_exists="replace", index=False)
                
                # 2. Upload data to the temporary table
                df.to_sql("temp_orders", conn, if_exists="append", index=False)
                
                # 3. Perform the UPSERT via DELETE + INSERT.
                # Build quoted column names for safe SQL execution
                target_cols = [f'"{col}"' for col in df.columns]
                
                # Handle specific transformations in the SELECT (e.g., Date vs CAST(Date AS DATE))
                select_cols = []
                for col in df.columns:
                    if col.lower() == 'date':
                        select_cols.append(f'CAST("{col}" AS DATE)')
                    else:
                        select_cols.append(f'"{col}"')

                cols_str = ", ".join(target_cols)
                select_str = ", ".join(select_cols)
                
                # UPSERT LOGIC for pp_wastage and pp_waste:
                if table_name == "pp_wastage":
                    delete_query = f"""
                        DELETE FROM "{schema}"."{table_name}" T
                        USING temp_orders S
                        WHERE T."Outlet" = S."Outlet"
                          AND T."Date" = CAST(S."Date" AS DATE)
                          AND T."Raw Material" = S."Raw Material";
                    """
                elif table_name == "pp_waste":
                    delete_query = f"""
                        DELETE FROM "{schema}"."{table_name}" T
                        USING temp_orders S
                        WHERE T."Outlet_Name" = S."Outlet_Name"
                          AND T."Date" = CAST(S."Date" AS DATE)
                          AND T."Item_Name" = S."Item_Name";
                    """
                else:
                    # Fallback for other tables like pp_orders
                    conflict_col = next((c for c in ["Invoice No", "Invoice_No", "invoice_no"] if c in df.columns), "invoice_no")
                    delete_query = f"""
                        DELETE FROM "{schema}"."{table_name}"
                        WHERE "{conflict_col}" IN (SELECT "{conflict_col}" FROM temp_orders);
                    """

                insert_query = f"""
                    INSERT INTO "{schema}"."{table_name}" ({cols_str})
                    SELECT {select_str} FROM temp_orders;
                """

                conn.execute(text(delete_query))
                conn.execute(text(insert_query))
                conn.execute(text("DROP TABLE temp_orders;"))
                
                self.logger.info(f"Successfully upserted {len(df)} records into {schema}.{table_name}.")
                return True

        except SQLAlchemyError as e:
            self.logger.error(f"SQLAlchemy Error during insertion: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during database insertion: {e}")
            return False

if __name__ == "__main__":
    # Quick test logic
    print("Testing PostgresUploader initialization...")
    try:
        uploader = PostgresUploader()
        print("Success.")
    except Exception as e:
        print(f"Failed: {e}")
