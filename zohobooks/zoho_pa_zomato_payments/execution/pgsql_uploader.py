
import os
import json
import pandas as pd
from sqlalchemy import create_engine, text, Numeric, DateTime, Text, inspect
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
            # Ensure table exists (create if not)
            inspector = inspect(self.engine)
            if not inspector.has_table(table_name, schema=self.db_schema):
                self.logger.info(f"Table {table_name} does not exist. Creating...")
                # Use to_sql to create the table structure
                df.head(0).to_sql(table_name, self.engine, schema=self.db_schema, if_exists="replace", index=False)

            with self.engine.begin() as conn:
                # 1. Create temp table
                df.to_sql("temp_upload", conn, if_exists="replace", index=False)
                
                # 2. TARGETED DELETE: Replace ONLY matching records for the keys being uploaded.
                self.logger.info(f"Synchronizing records for {table_name} (Targeted Upsert)...")
                
                # Build dynamic WHERE clause based on keys
                where_clauses = []
                for k in keys:
                    if k in ["Month", "Date"]:
                        where_clauses.append(f't."{k}" = CAST(tmp."{k}" AS TIMESTAMP)')
                    elif k in ["GST", "Amount", "Total", "Debit", "Credit", "Taxable Value", "Balance Amount", "Net Sales", "Total Sales"]:
                        where_clauses.append(f't."{k}" = CAST(tmp."{k}" AS NUMERIC)')
                    else:
                        where_clauses.append(f't."{k}" = tmp."{k}"')
                
                where_str = " AND ".join(where_clauses)
                
                delete_query = text(f'''
                    DELETE FROM "{self.db_schema}"."{table_name}" t
                    WHERE EXISTS (
                        SELECT 1 FROM temp_upload tmp 
                        WHERE {where_str}
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
