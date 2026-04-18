"""
Petpooja Wastage/Stock Summary Report Data Cleaner Module.

Handles cleaning and transformation of Petpooja Stock Summary reports
downloaded from inventory.petpooja.com for the pp_wastage table.
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, Union

import pandas as pd
from execution.logger_helper import LoggerHelper


class DataCleaner:
    """Handles cleaning and transformation of Petpooja Stock Summary reports."""

    def __init__(self, settings_path: Union[str, Path] = "settings.json") -> None:
        """Initialize the DataCleaner."""
        self.settings_path = Path(settings_path)
        self.settings: Dict[str, Any] = self._load_settings()
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger

        self.profile_dir = Path(self.settings.get("playwright_profile_dir", "/home/mcsuser/work/rwppdatatransfer/playwrightprofile/"))
        self.download_dir = Path(self.settings.get("download_dir", self.profile_dir / "downloads"))
        self.processed_dir = Path(self.settings.get("processed_dir", self.download_dir / "processed"))
        
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"DataCleaner initialized for pp_wastage. Download={self.download_dir}")

    def _load_settings(self) -> Dict[str, Any]:
        """Load global app settings."""
        if not self.settings_path.exists():
            return {}
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_download_dir(self) -> None:
        """Purge stale files."""
        removed_count = 0
        for file_path in self.download_dir.glob("*"):
            if file_path.is_file() and file_path.suffix.lower() in [".csv", ".xlsx"]:
                file_path.unlink()
                removed_count += 1
        if removed_count > 0:
            self.logger.info(f"Purged {removed_count} stale files.")

    def merge_all_reports(self, report_date: datetime.date = None) -> Optional[Path]:
        """Merge all individual outlet reports into one master file."""
        files = [
            f for f in self.download_dir.iterdir()
            if f.is_file() and f.suffix.lower() in [".csv", ".xlsx"]
            and f.parent == self.download_dir
        ]

        if not files:
            self.logger.info("No reports found to merge.")
            return None

        all_dfs = []
        for file_path in files:
            try:
                self.logger.info(f"Processing: {file_path.name}")
                df = self._read_file(file_path)
                if df is None or df.empty:
                    continue
                
                # Extract outlet name from filename: YYYY-MM-DD_Outlet_Name_report.xlsx
                parts = file_path.stem.split("_")
                outlet_name = " ".join(parts[1:-1]) if len(parts) >= 3 else "Unknown"

                df_cleaned = self._transform_data(df, outlet_name=outlet_name, report_date=report_date)
                if not df_cleaned.empty:
                    all_dfs.append(df_cleaned)
            except Exception as e:
                self.logger.error(f"Error processing {file_path.name}: {e}")

        if not all_dfs:
            return None

        master_df = pd.concat(all_dfs, ignore_index=True)
        
        # Archive
        for file_path in files:
            try:
                shutil.move(str(file_path), str(self.processed_dir / file_path.name))
            except:
                pass

        output_path = self.download_dir / f"Master_Wastage_Report_{datetime.now().strftime('%H%M%S')}.xlsx"
        master_df.to_excel(output_path, index=False)
        return output_path

    def _read_file(self, file_path: Path) -> Optional[pd.DataFrame]:
        """Read CSV, Excel, or HTML-based Excel with header discovery."""
        if file_path.suffix.lower() == ".csv":
            try:
                return pd.read_csv(file_path)
            except:
                return pd.read_csv(file_path, encoding='windows-1252')
        
        # Try reading as HTML first (common for Petpooja exports)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if '<html' in content.lower() or '<table' in content.lower():
                    dfs = pd.read_html(file_path)
                    if dfs:
                        df = dfs[0]
                        
                        # Find the actual header row
                        header_idx = -1
                        for idx, row in df.iterrows():
                            row_str = " ".join([str(v).lower() for v in row if pd.notna(v)])
                            if 'raw material' in row_str or 'item name' in row_str:
                                header_idx = idx
                                break
                        
                        if header_idx != -1:
                            # Re-assign headers
                            new_cols = [str(c).strip() for c in df.iloc[header_idx]]
                            df.columns = new_cols
                            df = df[header_idx + 1:].reset_index(drop=True)
                            self.logger.info(f"Found HTML header at row {header_idx}")
                            return df
                        return df
        except Exception as e:
            self.logger.debug(f"Not an HTML file or error reading HTML: {e}")

        # Try standard Excel reading
        try:
            df_peek = pd.read_excel(file_path, nrows=30, header=None)
            skip = 0
            for idx, row in df_peek.iterrows():
                vals = [str(v).lower() for v in row if pd.notna(v)]
                if any('item' in v or 'raw material' in v for v in vals):
                    skip = idx
                    break
            return pd.read_excel(file_path, skiprows=skip)
        except Exception as e:
            self.logger.error(f"Failed to read Excel file {file_path.name}: {e}")
            return None

    def _transform_data(self, df: pd.DataFrame, outlet_name: str, report_date: datetime.date) -> pd.DataFrame:
        """Apply transformation for Petpooja.pp_wastage schema."""
        df = df.copy()
        
        # Clean column names aggressively: lowercase, underscores, remove parentheses and special chars
        import re
        def clean_col(c):
            c = str(c).lower()
            c = re.sub(r'\(.*?\)', '', c) # Remove anything in parentheses
            c = re.sub(r'[^a-z0-9]+', '_', c) # Replace non-alphanumeric with underscore
            return c.strip('_')

        df.columns = [clean_col(c) for c in df.columns]

        # Numeric Conversion for all possible financial columns
        # We look for the cleaned keys
        numeric_targets = [
            'opening', 'purchase_sales_return', 'excess', 'total_stock',
            'consumed', 'wastage', 'normal_loss', 'sales_transfer_purchase_return',
            'shortage', 'conversion', 'production', 'total_consumed', 'closing_stock',
            'closing_summary', 'difference'
        ]
        
        for col in df.columns:
            if any(key in col for key in numeric_targets):
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '').str.replace('₹', ''), errors='coerce').fillna(0)

        # Drop summary rows
        if 'raw_material' in df.columns:
            df = df[~df['raw_material'].astype(str).str.lower().str.contains('total', na=False)]
        elif 'item_name' in df.columns:
            df = df[~df['item_name'].astype(str).str.lower().str.contains('total', na=False)]

        # Metadata
        df['Date'] = report_date if report_date else datetime.now().date()
        df['Outlet'] = outlet_name
        
        # Add Month column (derived from Date)
        # We use strftime('%B') for full month name like "April"
        try:
            df['Month'] = pd.to_datetime(df['Date']).dt.strftime('%B')
        except Exception as e:
            self.logger.warning(f"Failed to create Month column: {e}")
            df['Month'] = None
        
        # Zone Mapping
        jr_zone = ["Pink Adrak", "Pink Adrak Satkar"]
        hr_zone = ["Pink Adrak HBP", "Pink Adrak ABC", "Pink Adrak - Elan Epic", "Pink Adrak - BS", "Pink Adrak - Sector 31"]
        
        if outlet_name in jr_zone:
            df['Zone'] = 'JR Zone'
        elif outlet_name in hr_zone:
            df['Zone'] = 'HR Zone'
        else:
            df['Zone'] = 'General'

        # Schema Mapping (Input Excel -> DB Table)
        mapping = {
            'raw_material': 'Raw Material',
            'item_name': 'Raw Material',
            'unit': 'Unit',
            'opening': 'Opening (A)',
            'purchase_sales_return': 'Purchase / Sales Return (B)',
            'excess': 'Excess (C)',
            'total_stock': 'Total Stock (A+B+C)',
            'consumed': 'Consumed (D)',
            'wastage': 'Wastage (E)',
            'normal_loss': 'Normal Loss (F)',
            'sales_transfer_purchase_return': 'Sales / Transfer / Purchase Return (G)',
            'shortage': 'Shortage (H)',
            'conversion': 'Conversion (I)',
            'production': 'Conversion (I)', # Production is often used instead of conversion
            'total_consumed': 'Total Consumed (D+E+F+G+H)',
            'closing_stock': 'Closing Stock',
            'closing_summary': 'Closing Summary (A+B-D-E-F-G+I)',
            'difference': 'Difference'
        }
        df = df.rename(columns=mapping)
        
        target_cols = [
            'Zone', 'Outlet', 'Date', 'Month', 'Raw Material', 'Unit', 'Opening (A)', 
            'Purchase / Sales Return (B)', 'Excess (C)', 'Total Stock (A+B+C)', 
            'Consumed (D)', 'Wastage (E)', 'Normal Loss (F)', 
            'Sales / Transfer / Purchase Return (G)', 'Shortage (H)', 
            'Conversion (I)', 'Total Consumed (D+E+F+G+H)', 'Closing Stock', 
            'Closing Summary (A+B-D-E-F-G+I)', 'Difference'
        ]
        
        for c in target_cols:
            if c not in df.columns:
                df[c] = 0 if c not in ['Zone', 'Outlet', 'Date', 'Raw Material', 'Unit'] else None
        
        # Safety Filter
        df = df.dropna(subset=['Raw Material', 'Date', 'Outlet'])
                
        return df[target_cols]
