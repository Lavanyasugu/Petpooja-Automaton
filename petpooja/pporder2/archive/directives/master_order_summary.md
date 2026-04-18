# SOP: Master Order Summary Report Automation

## Goal
Automate the daily download of the Master Order Summary Report from Petpooja and track completion.

## Inputs
- Petpooja credentials (from `.env`)
- Target URL: `https://billing.petpooja.com/reports/order_summary_ho`
- Last processed date (from SQLite DB)

## Process
1. **Initialize DB**: Connect to `petpooja_automation.db`.
2. **Determine Target Date**:
    - Get the last processed date from `processed_dates` table.
    - If none, default to yesterday.
    - Otherwise, set target date = `last_processed_date + 1`.
3. **Launch Stealth Browser**: Use `nodriver` to open `https://billing.petpooja.com/reports/order_summary_ho`.
4. **Login Handling**:
    - If redirected to login page, enter credentials and submit.
    - Wait for dashboard/report page load.
5. **Navigate to Report**: Ensure we are on the Master Order Summary HO page.
6. **Date Selection**:
    - Select "From Date" and "To Date" as the target date.
    - Click "Export".
7. **File Download**:
    - Capture the download link generated.
    - Download the file using `requests` or similar to the configured folder in `settings.json`.
8. **Update DB**: Mark the date as `COMPLETED` in the database with the file path.

## Error Handling
- If login fails, log error and retry once.
- If export button is not found, log error and terminate.
- If download fails, mark date as `FAILED` in DB.
