"""
PostgreSQL Uploader Module for Petpooja KOT Reports.
Handles upserts for the Petpooja.pp_kot-reports table.
"""

import os
import json
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from execution.logger_helper import LoggerHelper

class PostgresUploader:
    def __init__(self, settings_path="settings.json"):
        load_dotenv()
        self.logger = LoggerHelper().logger
        
        with open(settings_path, 'r') as f:
            self.settings = json.load(f)
            
        self.db_host = self.settings.get("db_host")
        self.db_port = self.settings.get("db_port", "5432")
        self.db_name = self.settings.get("db_name")
        self.db_user = self.settings.get("db_user")
        self.db_pass = os.getenv("DB_PASS", self.settings.get("db_pass"))
        self.db_schema = self.settings.get("db_schema", "Petpooja")
        self.db_table = self.settings.get("db_table", "pp_kot-reports")

        self.conn_str = f"postgresql+psycopg2://{self.db_user}:{self.db_pass}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=require"
        self.engine = create_engine(self.conn_str)

    def upload_to_postgres(self, file_path):
        """Perform a Delete-then-Insert upsert."""
        df = pd.read_excel(file_path)
        if df.empty: return False

        try:
            with self.engine.begin() as conn:
                # 1. Create temp table
                df.to_sql('temp_kot', conn, if_exists='replace', index=False)
                
                # 2. Delete existing records to prevent duplicates
                # Key: Outlet + Date + KOT ID + Item Name
                delete_query = text(f'''
                    DELETE FROM "{self.db_schema}"."{self.db_table}"
                    WHERE ("Outlet", "Date", "KOT ID", "Item Name") IN (
                        SELECT "Outlet", CAST("Date" AS DATE), "KOT ID", "Item Name" FROM temp_kot
                    )
                ''')
                conn.execute(delete_query)
                
                # 3. Insert fresh records with casting
                cols = [f'"{c}"' for c in df.columns]
                col_string = ", ".join(cols)
                
                select_parts = []
                for c in df.columns:
                    if c.lower() in ["date", "punch time", "prepared time"]:
                        select_parts.append(f'CAST("{c}" AS TIMESTAMP)')
                    else:
                        select_parts.append(f'"{c}"')
                select_string = ", ".join(select_parts)

                insert_query = text(f'''
                    INSERT INTO "{self.db_schema}"."{self.db_table}" ({col_string})
                    SELECT {select_string} FROM temp_kot
                ''')
                conn.execute(insert_query)
                
                self.logger.info(f"Successfully upserted {len(df)} records into {self.db_table}")
                return True
        except Exception as e:
            self.logger.error(f"PostgreSQL upload failed: {e}")
            return False
