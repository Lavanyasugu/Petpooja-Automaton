"""
Petpooja KOT Report Data Cleaner Module.
Maps custom report fields to the Petpooja.pp_kot-reports schema.
"""

import os
import json
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from execution.logger_helper import LoggerHelper

class DataCleaner:
    def __init__(self, settings_path: str = "settings.json"):
        self.settings_path = Path(settings_path)
        with open(self.settings_path, 'r') as f:
            self.settings = json.load(f)
        
        self.logger = LoggerHelper().logger
        self.download_dir = Path(self.settings.get("download_dir"))
        self.processed_dir = Path(self.settings.get("processed_dir"))
        
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _load_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists(): return {}
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_download_dir(self):
        """Purge all report files from the download directory."""
        if not self.download_dir.exists(): return
        removed_count = 0
        for file_path in self.download_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in [".csv", ".xlsx"]:
                file_path.unlink()
                removed_count += 1
        if removed_count > 0:
            self.logger.info(f"Purged {removed_count} stale files.")

    def merge_all_reports(self, report_date: datetime.date = None) -> Optional[Path]:
        """Merge all individual outlet reports into one master file."""
        files = [f for f in self.download_dir.iterdir() if f.is_file() and "KOT_" in f.name]
        if not files: return None

        all_dfs = []
        for file_path in files:
            try:
                self.logger.info(f"Processing: {file_path.name}")
                df = self._read_file(file_path)
                if df is None or df.empty: continue
                
                parts = file_path.stem.split("_")
                outlet_name = " ".join(parts[2:]) if len(parts) >= 3 else "Unknown"

                df_cleaned = self._transform_data(df, outlet_name=outlet_name)
                if not df_cleaned.empty:
                    all_dfs.append(df_cleaned)
            except Exception as e:
                self.logger.error(f"Error processing {file_path.name}: {e}")

        if not all_dfs: return None

        master_df = pd.concat(all_dfs, ignore_index=True)
        
        # Archive
        for file_path in files:
            try: shutil.move(str(file_path), str(self.processed_dir / file_path.name))
            except: pass

        output_path = self.download_dir / f"Master_KOT_Report_{datetime.now().strftime('%H%M%S')}.xlsx"
        master_df.to_excel(output_path, index=False)
        return output_path

    def _read_file(self, file_path: Path) -> Optional[pd.DataFrame]:
        """Read Binary Excel with fallback to HTML."""
        # Method 1: Try Binary Excel (Standard for Custom Reports)
        try:
            # Peek for header
            df_peek = pd.read_excel(file_path, header=None, nrows=20)
            skip = 0
            for idx, row in df_peek.iterrows():
                row_vals = [str(v).lower() for v in row if pd.notna(v)]
                if any('kot id' in v or 'item name' in v for v in row_vals):
                    skip = idx
                    break
            return pd.read_excel(file_path, skiprows=skip)
        except Exception as e:
            self.logger.debug(f"Binary Excel read failed: {e}. Trying HTML engine...")

        # Method 2: Try HTML Engine (Common for Daily Reports)
        try:
            dfs = pd.read_html(file_path)
            if dfs:
                df = dfs[0]
                header_idx = -1
                for idx, row in df.iterrows():
                    row_str = " ".join([str(v).lower() for v in row if pd.notna(v)])
                    if 'kot id' in row_str or 'item name' in row_str:
                        header_idx = idx
                        break
                if header_idx != -1:
                    new_cols = [str(c).strip() for c in df.iloc[header_idx]]
                    df.columns = new_cols
                    df = df[header_idx + 1:].reset_index(drop=True)
                    return df
            return None
        except Exception as e:
            self.logger.error(f"Failed all read methods for {file_path.name}: {e}")
            return None

    def _transform_data(self, df: pd.DataFrame, outlet_name: str) -> pd.DataFrame:
        """Apply transformation for Petpooja.pp_kot-reports schema."""
        df = df.copy()
        
        # Standardize columns to lowercase for mapping
        df.columns = [str(c).strip().lower() for c in df.columns]

        # Mapping Dictionary
        header_map = {
            'kot id': 'KOT ID',
            'order type': 'Order Type',
            'item name': 'Item Name',
            'quantity': 'Qty',
            'qty': 'Qty',
            'item status': 'Item Status',
            'punch time': 'Punch Time',
            'prepared time': 'Prepared Time',
            'time taken': 'Preparation Time Taken (mins)'
        }
        
        # Filter and Rename
        cols_to_keep = [c for c in df.columns if c in header_map]
        df = df[cols_to_keep].rename(columns=header_map)
        
        # Add Global Fields
        df['Outlet'] = outlet_name
        
        # Zone Mapping
        jr_outlets = ["satkar", "hbp", "sector 31", "elan epic", "bs", "abc", "b2b"]
        df['Zone'] = df['Outlet'].apply(lambda x: 'JR Zone' if any(o in x.lower() for o in jr_outlets) else 'HR Zone')
        
        # Date and Month from Punch Time
        if 'Punch Time' in df.columns:
            # Handle potential non-string values
            df['Punch Time'] = pd.to_datetime(df['Punch Time'], errors='coerce')
            df = df.dropna(subset=['Punch Time'])
            df['Date'] = df['Punch Time'].dt.date
            df['Month'] = df['Punch Time'].dt.strftime('%B')
        
        # Final column order to match DB exactly
        target_order = [
            'Zone', 'Outlet', 'Month', 'Date', 'KOT ID', 'Order Type',
            'Item Name', 'Qty', 'Item Status', 'Punch Time', 
            'Prepared Time', 'Preparation Time Taken (mins)'
        ]
        
        for col in target_order:
            if col not in df.columns:
                df[col] = None
                
        return df[target_order]
