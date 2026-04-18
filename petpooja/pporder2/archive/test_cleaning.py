"""
Test script for DataCleaner.
Generates a mock Petpooja report and verifies transformation logic.
"""

import pandas as pd
import os
import json
from pathlib import Path
from execution.data_cleaner import DataCleaner

def create_mock_report(download_dir: Path):
    data = {
        "restaurant_name": ["Rest1"] * 10,
        "invoice_no": range(1001, 1011),
        "gst_no": ["GST123"] * 10,
        "date": ["2026-01-24"] * 10,
        "kot_no": range(1, 11),
        "payment_type": ["Cash"] * 10,
        "payment_description": ["Desc"] * 10,
        "order_type": [
            "Delivery(Parcel)", # Row 0 -> should become Delivery
            "Delivery (Parcel)",# Row 1 -> should become Delivery
            "Dine In",          # Row 2
            "Delivery",         # Row 3
            "Delivery",         # Row 4
            "Takeaway",         # Row 5
            "Delivery",         # Row 6
            "Staff",            # Row 7 -> should be deleted
            "Delivery",         # Row 8
            "Delivery"          # Row 9
        ],
        "status": [
            "Settled",          # 0
            "Settled",          # 1
            "Cancelled",        # 2 -> should be deleted
            "Complimentary",    # 3 -> should be deleted
            "Settled",          # 4
            "Settled",          # 5
            "Settled",          # 6
            "Settled",          # 7
            "Settled",          # 8
            "Staff"             # 9 -> should be deleted
        ],
        "sub_order_type": [
            "Zomato - Pink",    # 0 -> should become Zomato
            "Pink - Swiggy",    # 1 -> should become Swiggy
            "Dine In",          # 2
            "Fudr Online",      # 3 -> should become App
            "Fudr Online",      # 4 -> should become App -> then Delivery (since order_type is Delivery)
            "B2B",              # 5 -> should become Takeaway (order_type)
            "App",              # 6 -> should become Delivery (since order_type is Delivery)
            "Staff",            # 7
            "Swiggy",           # 8
            "App"               # 9
        ],
        "my_amount": [100.5] * 10,
        "total_tax": [10] * 10,
        "discount": [0] * 10,
        "delivery_charge": [20] * 10,
        "container_charge": [5] * 10,
        "service_charge": [0] * 10,
        "additional_charge": [0] * 10,
        "waived_off": [0] * 10,
        "round_off": [0.5] * 10,
        "total": [136.0] * 10,
        "gst_no": ["DELETE ME"] * 10, # Extra check
        "customer_phone": ["123"] * 10,
        "persons": [2] * 10
    }
    df = pd.DataFrame(data)
    mock_file = download_dir / "mock_report.xlsx"
    df.to_excel(mock_file, index=False)
    print(f"Created mock report at {mock_file}")
    return mock_file

def test_cleaning():
    # Load settings to find download_dir
    with open("settings.json", "r") as f:
        settings = json.load(f)
    download_dir = Path(settings.get("download_dir", ".tmp/downloads"))
    download_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create mock data
    mock_file = create_mock_report(download_dir)

    # 2. Run cleaner
    cleaner = DataCleaner()
    output_path = cleaner.process_latest_report()

    if output_path and output_path.exists():
        print(f"Cleaned report generated at {output_path}")
        df = pd.read_excel(output_path)
        
        print("\nVerification:")
        print(f"Final Row Count: {len(df)} (Expected < 10)")
        print(f"Columns: {df.columns.tolist()}")
        
        # Check order_type normalization
        print(f"Order Types: {df['order_type'].unique()}")
        
        # Check sub_order_type standardization
        print(f"Sub Order Types: {df['sub_order_type'].unique()}")
        
        # Check pruning
        pruned_cols = ["gst_no", "customer_phone", "persons"]
        for col in pruned_cols:
            if col in df.columns:
                print(f"FAILURE: Column {col} was NOT pruned.")
            else:
                print(f"SUCCESS: Column {col} was pruned.")
                
        # Check "Staff" removal
        if "Staff" in df.values:
             print("FAILURE: 'Staff' value still exists in dataframe.")
        else:
             print("SUCCESS: 'Staff' rows removed.")

    else:
        print("FAILURE: Cleaned report was not generated.")

if __name__ == "__main__":
    test_cleaning()
