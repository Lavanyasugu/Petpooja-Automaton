
import os
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, BrowserContext, Page
from execution.logger_helper import LoggerHelper

class ZohoExpenseAutomation:
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
            self.logger.info(f"Starting Expense Automation for {self.settings['org_name']} (Date: {run_date})")
            context = await p.firefox.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1366, "height": 768}
            )
            context.set_default_navigation_timeout(90000)
            context.set_default_timeout(60000)
            page = await context.new_page()
            
            try:
                # 1. Navigate
                self.logger.info(f"Navigating to {self.settings['org_name']} Expenses...")
                await page.goto(self.settings['url'], wait_until="load")
                await asyncio.sleep(20)

                # Check for Blocked message
                content = await page.content()
                if "blocked" in content.lower() and "security reasons" in content.lower():
                    self.logger.error("Zoho Security Block detected.")
                    return None

                # 2. Trigger Export (Two-step)
                self.logger.info("Opening More Actions menu...")
                await page.locator("button[aria-label='More Actions']").first.click()
                await asyncio.sleep(5)

                self.logger.info("Clicking 'Export' sub-menu trigger...")
                await page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('.dropdown-item, a, li, span, button'));
                    const target = items.find(el => el.textContent.trim() === 'Export' && !!(el.offsetWidth || el.offsetHeight));
                    if (target) target.click();
                }''')
                await asyncio.sleep(5)
                
                self.logger.info("Clicking 'Export Expenses' from sub-menu...")
                await page.evaluate('''() => {
                    const items = Array.from(document.querySelectorAll('button, a, li, span'));
                    const target = items.find(el => el.textContent.trim() === 'Export Expenses' && !!(el.offsetWidth || el.offsetHeight));
                    if (target) target.click();
                }''')
                await asyncio.sleep(8)

                # 3. Form Handling
                await page.wait_for_selector(".modal-content", timeout=60000)
                
                self.logger.info("Selecting 'Specific Period' radio button...")
                await page.evaluate('''() => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const target = labels.find(l => l.textContent.includes('Specific Period'));
                    if (target) target.click();
                }''')
                await asyncio.sleep(5)

                # Step 3b: Enter Dates
                dt = datetime.strptime(run_date, "%Y-%m-%d")
                formatted_date = dt.strftime("%d/%m/%Y")
                
                self.logger.info(f"Entering date range: {formatted_date}")
                date_inputs = page.locator(".modal-body input[placeholder*='dd/MM/yyyy']")
                
                if await date_inputs.count() >= 2:
                    for i in range(2):
                        await date_inputs.nth(i).click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await date_inputs.nth(i).type(formatted_date, delay=100)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(2)
                
                # Select XLSX
                await page.evaluate('''() => {
                    const labels = Array.from(document.querySelectorAll('label'));
                    const xlsx = labels.find(l => l.textContent.trim().includes('XLSX'));
                    if (xlsx) xlsx.click();
                }''')
                await asyncio.sleep(5)

                # 4. Download
                try:
                    async with page.expect_download(timeout=120000) as download_info:
                        self.logger.info("Clicking final Export button...")
                        await page.locator(".modal-footer button[type='submit']").first.click(force=True)
                    
                    download = await download_info.value
                    save_path = self.download_dir / f"expense_{run_date.replace('-','')}.xlsx"
                    await download.save_as(str(save_path))
                    self.logger.info(f"Successfully downloaded: {save_path}")
                    return str(save_path)
                except Exception as e:
                    self.logger.warning(f"Download event did not trigger: {e}")
                    return None

            except Exception as e:
                self.logger.error(f"Automation failed: {e}")
                await page.screenshot(path="error_expense.png")
                return None
            finally:
                await context.close()
