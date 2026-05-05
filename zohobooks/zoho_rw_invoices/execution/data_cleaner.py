
import pandas as pd
import numpy as np
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

    def process_invoices(self, file_path):
        self.logger.info(f"Cleaning Invoice report: {file_path}")
        try:
            df = pd.read_excel(file_path)
        except:
            df = pd.read_csv(file_path)
            
        if df.empty: return df
            
        df.columns = [str(c).strip() for c in df.columns]
        
        mapping = {
            'Invoice Date': 'Month',
            'Invoice Number': 'Invoice No.',
            'Customer Name': 'Outlet',
            'Total': 'Total Sales',
            'GST': 'GST',
            'SGST': 'SGST',
            'CGST': 'CGST',
            'IGST': 'IGST'
        }
        df = df.rename(columns=mapping)
        
        if 'Month' in df.columns:
            df['Month'] = pd.to_datetime(df['Month'], errors='coerce')
            
        numeric_cols = ['Total Sales', 'GST', 'SGST', 'CGST', 'IGST']
        for col in numeric_cols:
            if col not in df.columns:
                df[col] = 0.0
            else:
                if df[col].dtype == object:
                    df[col] = df[col].str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        agg_func = {
            'Month': 'first',
            'Total Sales': 'sum',
            'GST': 'sum',
            'SGST': 'sum',
            'CGST': 'sum',
            'IGST': 'sum'
        }
        agg_func = {k: v for k, v in agg_func.items() if k in df.columns}
        
        df = df.groupby(['Invoice No.', 'Outlet'], as_index=False).agg(agg_func)
        df['Net Sales'] = df['Total Sales'] - (df['SGST'] + df.get('CGST', 0.0) + df.get('IGST', 0.0))
        df['Zone'] = df['Outlet'].apply(self._map_zone)

        target_cols = ['Month', 'Invoice No.', 'Outlet', 'Total Sales', 'GST', 'SGST', 'CGST', 'IGST', 'Net Sales', 'Zone']
        for col in target_cols:
            if col not in df.columns:
                df[col] = None
        
        return df[target_cols]
