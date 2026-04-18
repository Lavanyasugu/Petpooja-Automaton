# Petpooja + Playwright Server Deployment Guide
*(Last Updated: March 2, 2026)*

Use this checklist to deploy the Petpooja automation to a clean Linux/Debian server using the strictly headless Playwright-Firefox engine.

## 1. Required Files and Folders 
You must transfer the following exact structure from your local PC to the remote server. 

### Folders
- `execution/` (Copy all contents)
- `.tmp/playwright_profile/` (Copy the **entire directory as-is**. This contains the 2FA-authorized session to bypass OTP!)
- `logs/` (Just create an empty folder on the server if it doesn't exist)
- `AWS/` (If applicable/needed for your specific infrastructure)

### Root Files Only
- `main.py` (Core pipeline logic)
- `.env` (Requires Petpooja & PostgreSQL credentials)
- `settings.json` (Mapped to correctly point to `.tmp/playwright_profile`)
- `requirements.txt` (Main dependency file)

### Supporting Files (Required for Setup)
- `archive/playwright_test.py` (Used locally if sessions expire; move to server if re-auth is needed)
- `archive/` (Keep specific supporting scripts here)

---

## 2. Excluded Files (DO NOT UPLOAD)
Do **not** upload the following files, as they are no longer in use and will clutter the server:
- `nodes_modules/` or any old `gdrive/` folders.
- `cookies.json` (Playwright stores cookies entirely inside `.tmp/playwright_profile/`).
- `execution/petpooja_requests.py` and `execution/export_cookies.py` (The fast API route is entirely deprecated).
- `.venv/` (Python virtual environments are system-specific and must be rebuilt on the server).
- `__pycache__/` folders.

---

## 3. Server Setup Instructions (Debian/Ubuntu)

Once all files are uploaded to your chosen directory (e.g., `~/petpooja_automation`), run these commands via SSH to initialize the headless environment:

**Step 3.1: Install Python & Create Virtual Environment**
```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
```

**Step 3.2: Install Python Requirements**
```bash
pip install -r requirements.txt
```

**Step 3.3: Install Playwright & Headless Firefox Dependencies**
*This is the most critical step for AWS Lightsail / Headless servers.*
```bash
playwright install firefox
playwright install-deps
```

**Step 3.4: Verify Execution**
Run the pipeline to test if the profile properly connects without OTP:
```bash
python main.py
```
*If everything is configured correctly, you will see `[INFO] [FALLBACK] Already authenticated via persistent profile` in the terminal output.*
