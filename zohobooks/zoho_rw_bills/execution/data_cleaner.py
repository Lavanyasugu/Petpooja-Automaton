
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

    def process_bills(self, file_path):
        self.logger.info(f"Cleaning Bill report: {file_path}")
        try:
            df = pd.read_excel(file_path)
        except:
            df = pd.read_csv(file_path)
            
        if df.empty: return df
        
        df.columns = [str(c).strip() for c in df.columns]
        
        # Updated mapping based on actual Zoho Export headers
        mapping = {
            'Vendor Name': 'Vendor',
            'GST Identification Number (GSTIN)': 'GST',
            'SubTotal': 'Taxable Value',
            'Bill Status': 'status',
            'Bill Number': 'Bill_Number',
            'Bill Date': 'Month',
            'Total': 'Amount',
            'Balance': 'Balance Amount',
            'Account': 'Category',
            'Branch Name': 'Location'
        }
        df = df.rename(columns=mapping)
        
        if 'Month' in df.columns:
            df['Month'] = pd.to_datetime(df['Month'], errors='coerce')
        
        for col in ['GST', 'Taxable Value', 'Amount', 'Balance Amount']:
            if col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        if 'Location' in df.columns:
            df['Zone'] = df['Location'].apply(self._map_zone)
        else:
            df['Zone'] = "JR Zone"

        target_cols = ['Vendor', 'GST', 'Taxable Value', 'status', 'Bill_Number', 
                       'Month', 'Amount', 'Balance Amount', 'Category', 'Location', 'Zone']
        
        # Ensure all target columns exist
        for col in target_cols:
            if col not in df.columns:
                df[col] = None
        
        return df[target_cols]
