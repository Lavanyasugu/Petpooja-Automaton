#!/bin/bash
# run_automation.sh - Wrapper script for daily Petpooja automation

# Navigate to the project directory
cd /home/admin/petpooja2/ppitemorderwise

# Create logs directory if it doesn't exist
mkdir -p logs

# Run the automation using the virtual environment's python
# It defaults to processing "yesterday" in IST.
echo "Starting automation run at $(date)" >> logs/cron.log
./venv/bin/python main.py >> logs/cron.log 2>&1
echo "Automation run finished at $(date) with exit code $?" >> logs/cron.log
echo "----------------------------------------------------" >> logs/cron.log
