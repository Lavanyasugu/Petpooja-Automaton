
import pandas as pd
import re
from execution.logger_helper import LoggerHelper

class DataCleaner:
    def __init__(self):
        self.logger = LoggerHelper().logger

    def _extract_platform(self, details):
        details = str(details).upper()
        if "ZOMATO" in details: return "Zomato"
        if "SWIGGY" in details: return "Swiggy"
        if "MAGICPIN" in details: return "Magicpin"
        if "DOTPE" in details: return "DotPe"
        return "Direct/Other"

    def _extract_outlet(self, details, branch=None):
        # Use branch name if available
        if branch and str(branch).strip() and str(branch).lower() != 'nan':
            return str(branch).strip()
            
        details = str(details).upper()
        # Common outlet keywords in Pink Adrak org
        if any(kw in details for kw in ["HBP", "ABC", "ELAN EPIC", "BS", "SECTOR 31", "AIPL", "SATKAR"]):
            for kw in ["HBP", "ABC", "ELAN EPIC", "BS", "SECTOR 31", "AIPL", "SATKAR"]:
                if kw in details: return kw
        return "Main/General"

    def process_clearing_account(self, file_path, from_date=None, to_date=None):
        self.logger.info(f"Cleaning Clearing Account report for zb_fudr-payments: {file_path}")
        try:
            # Read excel - handling potential multi-row headers
            df = pd.read_excel(file_path, skiprows=0)
            
            # Find the actual header row by looking for 'date' or 'transaction_id'
            header_row_idx = -1
            for idx, row in df.iterrows():
                row_vals = [str(v).strip().lower() for v in row.values]
                if 'date' in row_vals or 'transaction_id' in row_vals:
                    header_row_idx = idx
                    break
            
            if header_row_idx != -1:
                df.columns = [str(c).strip().lower() for c in df.iloc[header_row_idx]]
                df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
            else:
                self.logger.warning("Could not find standard Zoho header row. Attempting to use first row.")
                df.columns = [str(c).strip().lower() for c in df.columns]
        except Exception as e:
            self.logger.error(f"Error reading report: {e}")
            return pd.DataFrame()

        if df.empty: return df
        
        # Target columns: Month, platform, outlet, Debit, Credit, Amount, description
        
        # 1. Map Month (Date)
        if 'date' in df.columns:
            df['Month'] = pd.to_datetime(df['date'], errors='coerce')
        elif 'Month' not in df.columns:
            df['Month'] = None
        
        # Strictly filter by date range if provided
        if from_date and to_date:
            f_dt = pd.to_datetime(from_date)
            t_dt = pd.to_datetime(to_date)
            mask = (df['Month'] >= f_dt) & (df['Month'] <= t_dt)
            before_count = len(df)
            df = df.loc[mask].reset_index(drop=True)
            after_count = len(df)
            self.logger.info(f"Filtered records by date range {from_date} to {to_date}: {before_count} -> {after_count}")

        # 2. Map description (Transaction Details)
        if 'transaction_details' in df.columns:
            df['description'] = df['transaction_details']
        elif 'account' in df.columns:
            df['description'] = df['account']
        else:
            df['description'] = ""

        # 3. Extract platform and outlet
        df['platform'] = df['description'].apply(self._extract_platform)
        
        # Use branch_name if it exists in export
        branch_col = 'branch_name' if 'branch_name' in df.columns else None
        df['outlet'] = df.apply(lambda row: self._extract_outlet(row['description'], row.get(branch_col) if branch_col else None), axis=1)

        # 4. Map Money columns
        mapping = {
            'debit': 'Debit',
            'credit': 'Credit',
            'net_amount': 'Amount'
        }
        df = df.rename(columns=mapping)

        for col in ['Debit', 'Credit', 'Amount']:
            if col not in df.columns:
                df[col] = 0.0
            else:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace(',', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        # Final column selection
        target_cols = ['Month', 'platform', 'outlet', 'Debit', 'Credit', 'Amount', 'description']
        
        # Ensure all columns exist
        for col in target_cols:
            if col not in df.columns:
                df[col] = None

        # Filter out rows with no date (usually headers/footers in Excel exports)
        df = df.dropna(subset=['Month'])
        
        return df[target_cols]
