
import os
import json
import pandas as pd
from sqlalchemy import create_engine, text, Numeric, DateTime, Text
from execution.logger_helper import LoggerHelper

class PostgresUploader:
    def __init__(self):
        self.logger = LoggerHelper().logger
        with open("settings.json", "r") as f:
            self.settings = json.load(f)
            
        self.db_host = self.settings.get("db_host")
        self.db_port = self.settings.get("db_port", "5432")
        self.db_name = self.settings.get("db_name")
        self.db_user = self.settings.get("db_user")
        self.db_pass = os.getenv("DB_PASS")
        self.db_schema = self.settings.get("db_schema", "Zoho_Books")

        self.conn_str = f"postgresql+psycopg2://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        self.engine = create_engine(self.conn_str)

    def upload(self, df: pd.DataFrame, table_name: str, keys: list):
        if df.empty:
            return True

        try:
            with self.engine.begin() as conn:
                # 1. Create temp table
                df.to_sql("temp_upload", conn, if_exists="replace", index=False)
                
                # 2. TARGETED DELETE: Replace ONLY matching records for the dates being uploaded.
                self.logger.info(f"Synchronizing records for {table_name} (Targeted Upsert)...")
                
                # Determine date column name (Month or Date)
                date_col = "Month" if "Month" in df.columns else "Date"
                
                # Build delete query based on keys
                if "Journal Number" in df.columns:
                    delete_query = text(f'''
                        DELETE FROM "{self.db_schema}"."{table_name}" t
                        WHERE EXISTS (
                            SELECT 1 FROM temp_upload tmp 
                            WHERE t."Journal Number" = tmp."Journal Number"
                        )
                    ''')
                elif "Bill_Number" in df.columns:
                    delete_query = text(f'''
                        DELETE FROM "{self.db_schema}"."{table_name}" t
                        WHERE EXISTS (
                            SELECT 1 FROM temp_upload tmp 
                            WHERE t."Bill_Number" = tmp."Bill_Number"
                            AND t."Vendor" = tmp."Vendor"
                        )
                    ''')
                elif "Invoice No." in df.columns:
                    delete_query = text(f'''
                        DELETE FROM "{self.db_schema}"."{table_name}" t
                        WHERE EXISTS (
                            SELECT 1 FROM temp_upload tmp 
                            WHERE t."Invoice No." = tmp."Invoice No."
                            AND t."Outlet" = tmp."Outlet"
                        )
                    ''')
                else:
                    # Default for expenses or general
                    delete_query = text(f'''
                        DELETE FROM "{self.db_schema}"."{table_name}" t
                        WHERE EXISTS (
                            SELECT 1 FROM temp_upload tmp 
                            WHERE t.\"{date_col}\" = CAST(tmp.\"{date_col}\" AS TIMESTAMP)
                            AND t.\"Category\" = tmp.\"Category\"
                            AND t.\"Amount\" = CAST(tmp.\"Amount\" AS NUMERIC)
                        )
                    ''')
                
                conn.execute(delete_query)
                
                # 3. Insert from temp to main with explicit casting
                target_cols = [f'"{c}"' for c in df.columns]
                select_cols = []
                for c in df.columns:
                    if c in ["Month", "Date"]:
                        select_cols.append(f'CAST("{c}" AS TIMESTAMP)')
                    elif c in ["GST", "Amount", "Total", "Debit", "Credit", "Taxable Value", "Balance Amount", "Net Sales", "Total Sales"]:
                        select_cols.append(f'CAST("{c}" AS NUMERIC)')
                    else:
                        select_cols.append(f'"{c}"')
                
                cols_str = ", ".join(target_cols)
                select_str = ", ".join(select_cols)
                
                insert_query = text(f'INSERT INTO "{self.db_schema}"."{table_name}" ({cols_str}) SELECT {select_str} FROM temp_upload')
                conn.execute(insert_query)
                
                conn.execute(text("DROP TABLE temp_upload"))
                self.logger.info(f"Successfully synchronized {len(df)} records to {table_name}")
                return True
        except Exception as e:
            self.logger.error(f"Database upload failed for {table_name}: {e}")
            return False
