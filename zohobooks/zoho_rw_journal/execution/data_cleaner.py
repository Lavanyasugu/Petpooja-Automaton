
import pandas as pd
from execution.logger_helper import LoggerHelper

class DataCleaner:
    def __init__(self):
        self.logger = LoggerHelper().logger

    def _map_zone(self, outlet_name):
        name = str(outlet_name).upper()
        if any(kw in name for kw in ["HBP", "ABC", "ELAN EPIC", "BS", "SECTOR 31", "B2B"]):
            return "HR Zone"
        if any(kw in name for kw in ["SATKAR", "XC"]) or "PINK ADRAK" in name:
            return "JR Zone"
        return "JR Zone"

    def process_journals(self, file_path):
        self.logger.info(f"Cleaning Journal report: {file_path}")
        try:
            df = pd.read_excel(file_path)
        except:
            df = pd.read_csv(file_path)
            
        if df.empty: return df
        
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapping Zoho Journal columns to DB columns
        # Date, Zone, GST, Debit, Credit, Category, Total, Description
        mapping = {
            'Journal Date': 'Date',
            'Account': 'Category'
        }
        df = df.rename(columns=mapping)
        
        # Ensure numeric
        for col in ['Debit', 'Credit', 'Total']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        
        # Add missing columns
        df['Zone'] = "JR Zone" # Default
        df['GST'] = 0.0
        
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            df = df[df['Date'].notna()]

        target_cols = ['Date', 'Zone', 'GST', 'Debit', 'Credit', 'Category', 'Total', 'Description']
        
        # Filter only existing columns if some are still missing
        final_cols = [c for c in target_cols if c in df.columns]
        for col in target_cols:
            if col not in df.columns:
                df[col] = None
        
        return df[target_cols]
