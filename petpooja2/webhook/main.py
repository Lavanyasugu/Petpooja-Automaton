import subprocess
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks, Request
from typing import Optional, Any
from dotenv import load_dotenv

# Load env from webhook directory if exists
load_dotenv()

app = FastAPI()

# SECURITY: Use this key in your Cloud Scheduler Headers: X-API-Key: petpooja-secret-2026
API_KEY = os.getenv("WEBHOOK_API_KEY", "petpooja-secret-2026")

PROJECTS = {
    "waste": "/home/admin/petpooja2/ppwaste",
    "kot-reports": "/home/admin/petpooja2/ppkotreports",
    "item-wise-orders": "/home/admin/petpooja2/ppitemorderwise"
}

def send_summary_email(summary_data: list):
    """Sends a summary email of the daily automation run."""
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT")

    if not all([smtp_server, smtp_user, smtp_password, recipient]):
        print("Email settings missing in .env. Skipping email notification.")
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"Petpooja2 Automation Summary - {date_str}"
    
    body = f"<h2>Daily Automation Report (Petpooja2) - {date_str}</h2>"
    body += "<table border='1' cellpadding='5' style='border-collapse: collapse;'>"
    body += "<tr style='background-color: #f2f2f2;'><th>Project</th><th>Status</th></tr>"
    
    for item in summary_data:
        status_color = "green" if item['status'] == "Success" else "red"
        body += f"<tr><td>{item['name']}</td><td style='color: {status_color}; font-weight: bold;'>{item['status']}</td></tr>"
    
    body += "</table>"
    body += "<p>Detailed logs are available on the server at /home/admin/petpooja2/webhook/execution.log</p>"

    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"Summary email sent to {recipient}")
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

def run_script(project_path: str) -> bool:
    """Executes the main.py of a project using its own virtual environment."""
    venv_python = os.path.join(project_path, "venv/bin/python3")
    main_py = os.path.join(project_path, "main.py")
    
    print(f"Starting execution: {main_py}")
    try:
        process = subprocess.Popen(
            [venv_python, main_py],
            cwd=project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        with open("/home/admin/petpooja2/webhook/execution.log", "a") as f:
            f.write(f"\n--- Project: {project_path} ---\n")
            f.write(stdout)
            if stderr:
                f.write("\nERRORS:\n")
                f.write(stderr)
        
        return process.returncode == 0
    except Exception as e:
        with open("/home/admin/petpooja2/webhook/execution.log", "a") as f:
            f.write(f"\nFAILED to run {project_path}: {str(e)}\n")
        return False

@app.post("/trigger/{project_id}")
async def trigger_project(
    project_id: str, 
    background_tasks: BackgroundTasks,
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    # Optional: read body to prevent errors if Google sends one
    try:
        await request.json()
    except:
        pass

    if x_api_key != API_KEY:
        print(f"Invalid API Key attempt: {x_api_key}")
        raise HTTPException(status_code=403, detail="Invalid API Key")
    
    if project_id == "all":
        print("Triggering all projects...")
        background_tasks.add_task(run_all_projects)
        return {"status": "success", "message": "All projects in petpooja2 queued for sequential execution"}
    
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found in petpooja2")
    
    print(f"Triggering project: {project_id}")
    background_tasks.add_task(run_script, PROJECTS[project_id])
    return {"status": "success", "message": f"Project {project_id} in petpooja2 queued for execution"}

def run_all_projects():
    summary = []
    for name, path in PROJECTS.items():
        success = run_script(path)
        summary.append({
            "name": name,
            "status": "Success" if success else "Failed"
        })
    
    send_summary_email(summary)

@app.get("/health")
async def health():
    return {"status": "alive", "registry": "petpooja2"}

if __name__ == "__main__":
    import uvicorn
    # Using Port 5001 for Petpooja2 Webhook
    uvicorn.run(app, host="0.0.0.0", port=5001)
