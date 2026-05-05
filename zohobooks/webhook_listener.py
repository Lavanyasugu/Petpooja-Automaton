import subprocess
import os
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

# List of automation directories
AUTOMATIONS = [
    "zoho_pa_fudr_clearing",
    "zoho_pa_cash_clearing",
    "zoho_pa_upi_clearing",
    "zoho_pa_swiggy_payments",
    "zoho_pa_zomato_payments"
]

BASE_DIR = "/home/admin/work"

def run_automation(dir_name):
    path = os.path.join(BASE_DIR, dir_name)
    venv_python = os.path.join(path, "venv/bin/python3")
    main_script = os.path.join(path, "main.py")
    
    print(f"Starting automation: {dir_name}")
    try:
        result = subprocess.run([venv_python, main_script], cwd=path, capture_output=True, text=True)
        print(f"Finished {dir_name}. Output: {result.stdout}")
        if result.stderr:
            print(f"Error in {dir_name}: {result.stderr}")
    except Exception as e:
        print(f"Failed to run {dir_name}: {e}")

@app.route('/trigger-all', methods=['POST', 'GET'])
def trigger_all():
    # Run in background threads to avoid timeout for the scheduler
    for auto in AUTOMATIONS:
        thread = threading.Thread(target=run_automation, args=(auto,))
        thread.start()
    
    return jsonify({"status": "triggered", "message": f"Started {len(AUTOMATIONS)} automations in background."}), 200

if __name__ == '__main__':
    # Listen on all interfaces on port 5001
    app.run(host='0.0.0.0', port=5001)
