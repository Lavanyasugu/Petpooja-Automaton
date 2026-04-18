"""
Petpooja Report Data Cleaner Module for Itemwise Order Summary.

This module provides functionality to clean and transform Excel reports
downloaded from Petpooja for the order_summary_itemwise table.
"""

import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
from execution.logger_helper import LoggerHelper


class DataCleaner:
    """Handles cleaning and transformation of Petpooja Itemwise Excel reports."""

    def __init__(self, settings_path: str | Path = "settings.json") -> None:
        self.settings_path = Path(settings_path)
        self.settings: Dict[str, Any] = self._load_settings()
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger

        self.profile_dir = Path(os.getenv("PLAYWRIGHT_PROFILE_DIR", self.settings.get("playwright_profile_dir", "/home/admin/petpooja2/playwrightprofile/")))
        self.download_dir = Path(self.settings.get("download_dir", self.profile_dir / "downloads"))
        self.processed_dir = Path(self.settings.get("processed_dir", self.download_dir / "processed"))
        
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"DataCleaner paths initialized: Download={self.download_dir}, Processed={self.processed_dir}")

    def _load_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_download_dir(self) -> None:
        self.logger.info("Preserving files in download directory.")
        return

    def process_latest_report(self) -> Optional[Path]:
        files = [
            f
            for f in self.download_dir.iterdir()
            if f.is_file()
            and f.suffix.lower() in [".csv", ".xlsx"]
            and f.parent == self.download_dir
        ]

        if not files:
            self.logger.info("No reports found in download directory to clean.")
            return None

        latest_file = max(files, key=lambda f: f.stat().st_mtime)
        self.logger.info(f"Processing report: {latest_file.name}")

        try:
            self.logger.info(f"Reading input file: {latest_file.name}...")
            if latest_file.suffix.lower() == ".csv":
                df = pd.read_csv(latest_file)
            else:
                df = pd.read_excel(latest_file)

            cleaned_df = self._transform_data(df)

            try:
                date_part = latest_file.name.split("_")[0]
                processing_datetime = datetime.strptime(date_part, "%Y-%m-%d")
            except Exception:
                processing_datetime = datetime.now()

            output_filename = processing_datetime.strftime("%d %b Itemwise Sales.xlsx")
            output_path = self.download_dir / output_filename
            
            if output_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = self.download_dir / f"{processing_datetime.strftime('%d %b')} Itemwise Sales_{timestamp}.xlsx"

            self.logger.info(f"Saving cleaned report to: {output_path.name}...")
            cleaned_df.to_excel(output_path, index=False)

            # Move original to processed
            dest = self.processed_dir / latest_file.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(latest_file), str(dest))
            self.logger.info(f"Moved original file to processed folder: {dest.name}")

            return output_path

        except Exception as e:
            self.logger.error(f"Error cleaning report {latest_file.name}: {e}")
            return None

    def _transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Initializing Data Transformation for Itemwise schema...")
        df = df.copy()

        # 1. Column Normalization
        if "order_type" in df.columns:
            mask = df["order_type"].str.contains(r"Delivery\s?\(Parcel\)", case=False, na=False)
            df.loc[mask, "order_type"] = "Delivery"

        # 2. Filtering
        if "status" in df.columns:
            df = df[~df["status"].str.lower().isin(["cancelled", "complimentary"])]

        # 3. Numeric Conversion
        financial_cols = [
            "my_amount", "total_tax", "discount", "delivery_charge", 
            "container_charge", "service_charge", "additional_charge", 
            "deduction_charge", "waived_off", "round_off", "total",
            "item_price", "item_quantity", "item_total", "sap_code", "persons", "customer_phone"
        ]
        for col in financial_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # 4. Header Mapping
        header_map = {
            'restaurant_name': 'restaurant_name',
            'invoice_no': 'invoice_no',
            'date': 'date',
            'payment_type': 'payment_type',
            'sub_order_type': 'platform',
            'status': 'status',
            'area': 'area',
            'virtual_brand_name': 'brand_name',
            'brand_grouping': 'brand_grouping',
            'assign_to': 'assign_to',
            'customer_phone': 'customer_phone',
            'customer_name': 'customer_name',
            'customer_address': 'customer_address',
            'persons': 'persons',
            'order_cancel_reason': 'order_cancel_reason',
            'my_amount': 'my_amount',
            'total_tax': 'tax',
            'discount': 'discount',
            'delivery_charge': 'delivery_charge',
            'container_charge': 'container_charge',
            'service_charge': 'service_charge',
            'additional_charge': 'additional_charge',
            'deduction_charge': 'deduction_charge',
            'waived_off': 'waived_off',
            'round_off': 'round_off',
            'total': 'total',
            'item_name': 'item_name',
            'category_name': 'category_name',
            'sap_code': 'sap_code',
            'item_price': 'item_price',
            'item_quantity': 'item_quantity',
            'item_total': 'item_total'
        }
        
        df = df.rename(columns=header_map)
        
        if 'platform' not in df.columns and 'sub_order_type' in df.columns:
             df['platform'] = df['sub_order_type']
        elif 'platform' not in df.columns and 'order_type' in df.columns:
             df['platform'] = df['order_type']

        # Ensure Date is properly typed
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])

        # Final Cleanup: Target DB schema
        target_schema_cols = [
            'restaurant_name', 'invoice_no', 'date', 'payment_type', 'platform',
            'status', 'area', 'brand_name', 'brand_grouping', 'assign_to',
            'customer_phone', 'customer_name', 'customer_address', 'persons',
            'order_cancel_reason', 'my_amount', 'tax', 'discount',
            'delivery_charge', 'container_charge', 'service_charge',
            'additional_charge', 'deduction_charge', 'waived_off',
            'round_off', 'total', 'item_name', 'category_name',
            'sap_code', 'item_price', 'item_quantity', 'item_total'
        ]
        
        for col in target_schema_cols:
            if col not in df.columns:
                df[col] = None

        self.logger.info(f"Transformation complete. DataFrame shape: {df.shape}")
        return df[target_schema_cols]
