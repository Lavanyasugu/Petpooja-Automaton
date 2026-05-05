
import os
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, BrowserContext, Page
from execution.logger_helper import LoggerHelper

class ZohoInvoiceAutomation:
    def __init__(self, headless=True):
        self.logger = LoggerHelper().logger
        with open("settings.json", "r") as f:
            self.settings = json.load(f)
        
        self.profile_dir = Path(self.settings.get("playwright_profile_dir"))
        self.download_dir = Path(self.settings.get("download_dir", "./downloads"))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    async def run(self, run_date: str):
        async with async_playwright() as p:
            self.logger.info(f"Starting Invoice Automation for {self.settings['org_name']} (Date: {run_date})")
            context = await p.firefox.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1366, "height": 768}
            )
            context.set_default_navigation_timeout(90000)
            context.set_default_timeout(60000)
            page = await context.new_page()
            
            try:
                # 1. Establish Org Context
                self.logger.info(f"Navigating to {self.settings['org_name']} Invoices...")
                await page.goto(self.settings['url'], wait_until="load")
                await asyncio.sleep(20)

                # Check for Blocked message
                content = await page.content()
                if "blocked" in content.lower() and "security reasons" in content.lower():
                    self.logger.error("Zoho Security Block detected.")
                    return None

                # 2. Trigger Export (Two-step)
                self.logger.info("Opening More Actions menu...")
                more_btn = page.locator("button[aria-label='More Actions']").first
                await more_btn.click()
                await asyncio.sleep(8)

                self.logger.info("Clicking 'Export' sub-menu...")
                await page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('.dropdown-item, a, li, span, button'));
                    const target = items.find(el => el.textContent.trim() === 'Export' && !!(el.offsetWidth || el.offsetHeight));
                    if (target) target.click();
                }''')
                await asyncio.sleep(5)
                
                self.logger.info("Clicking 'Export Invoices'...")
                await page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('.dropdown-item, a, li, span, button'));
                    const target = items.find(el => el.textContent.trim() === 'Export Invoices' && !!(el.offsetWidth || el.offsetHeight));
                    if (target) target.click();
                }''')
                await asyncio.sleep(5)

                # 3. Form Handling
                await page.wait_for_selector(".modal-content, .export-dialog", timeout=60000)
                dt = datetime.strptime(run_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%d/%m/%Y")
                
                for label in ["From Date", "To Date"]:
                    selector = f"input[aria-label='{label}']"
                    await page.click(selector)
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    await page.keyboard.type(formatted_date, delay=100)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)

                # Select XLSX
                await page.evaluate('''() => {
                    const labels = Array.from(document.querySelectorAll('label, span'));
                    const xlsx = labels.find(l => l.textContent.trim() === 'XLSX');
                    if (xlsx) xlsx.click();
                }''')
                await asyncio.sleep(10)

                # 4. Download
                async with page.expect_download(timeout=300000) as download_info:
                    self.logger.info("Clicking final Export button...")
                    await page.evaluate('''() => {
                        const btns = Array.from(document.querySelectorAll('button'));
                        const exportBtn = btns.find(b => (b.textContent.trim() === 'Export' || b.textContent.trim() === 'Next') && b.offsetParent !== null);
                        if (exportBtn) exportBtn.click();
                    }''')
                
                download = await download_info.value
                save_path = self.download_dir / f"invoices_{run_date.replace('-','')}.xlsx"
                await download.save_as(str(save_path))
                self.logger.info(f"Successfully downloaded: {save_path}")
                return str(save_path)

            except Exception as e:
                self.logger.error(f"Automation failed: {e}")
                await page.screenshot(path="error_invoices.png")
                return None
            finally:
                await context.close()
