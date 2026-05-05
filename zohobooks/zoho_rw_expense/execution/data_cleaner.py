
import pandas as pd
from execution.logger_helper import LoggerHelper

class DataCleaner:
    def __init__(self):
        self.logger = LoggerHelper().logger

    def process_expenses(self, file_path):
        self.logger.info(f"Cleaning Expense report: {file_path}")
        try:
            df = pd.read_excel(file_path)
        except:
            df = pd.read_csv(file_path)
            
        if df.empty: return df
        
        df.columns = [str(c).strip() for c in df.columns]
        
        # Mapping based on verified Zoho Expense Export headers
        mapping = {
            'Expense Date': 'Month',
            'Expense Description': 'Description',
            'Expense Account': 'Category',
            'Branch Name': 'Outlet',
            'Tax Amount': 'GST',
            'Expense Amount': 'Amount',
            'Total': 'Total'
        }
        df = df.rename(columns=mapping)
        
        if 'Month' in df.columns:
            df['Month'] = pd.to_datetime(df['Month'], errors='coerce')
        
        for col in ['GST', 'Amount', 'Total']:
            if col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        target_cols = ['Month', 'Description', 'Category', 'Outlet', 'GST', 'Amount', 'Total']
        for col in target_cols:
            if col not in df.columns:
                df[col] = None
        
        return df[target_cols]
