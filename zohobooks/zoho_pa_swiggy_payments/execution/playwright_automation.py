
import os
import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright, Page
from execution.logger_helper import LoggerHelper

class ZohoReportAutomation:
    def __init__(self, headless=True):
        self.logger = LoggerHelper().logger
        with open("settings.json", "r") as f:
            self.settings = json.load(f)
        
        self.profile_dir = Path(self.settings.get("playwright_profile_dir"))
        self.download_dir = Path(self.settings.get("download_dir", "./downloads"))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless

    async def run(self, from_date: str, to_date: str, account_name: str):
        async with async_playwright() as p:
            self.logger.info(f"Starting Report Automation for {self.settings['org_name']} | Account: {account_name}")
            context = await p.firefox.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1366, "height": 768}
            )
            context.set_default_navigation_timeout(90000)
            context.set_default_timeout(60000)
            page = await context.new_page()
            
            try:
                # 1. Navigate to Balance Sheet
                self.logger.info("Navigating to Balance Sheet...")
                await page.goto(self.settings['url'], wait_until="load")
                await asyncio.sleep(20)

                # 2. Click on the Account link
                self.logger.info(f"Searching for '{account_name}' link...")
                
                found_link = False
                for frame in page.frames:
                    try:
                        # Find the link and click it
                        clicked = await frame.evaluate(f'''(name) => {{
                            const links = Array.from(document.querySelectorAll('a'));
                            const target = links.find(a => a.textContent.includes(name));
                            if (target) {{
                                target.scrollIntoView();
                                target.click();
                                return true;
                            }}
                            return false;
                        }}''', account_name)
                        if clicked:
                            found_link = True
                            self.logger.info(f"Link '{account_name}' clicked in frame: {frame.name or frame.url}")
                            break
                    except:
                        continue
                
                if not found_link:
                    # Try a broader text search
                    await page.locator(f"text={account_name}").first.click()
                
                await asyncio.sleep(15)
                self.logger.info("Drilled down into Account Transactions.")

                # 3. Set Custom Date Range via URL manipulation (Robust)
                self.logger.info("Setting Date Range via URL...")
                
                # We need to wait for the URL to reflect the drilled down state
                await asyncio.sleep(5)
                current_url = page.url
                if "from_date=" in current_url and "to_date=" in current_url:
                    # Update dates in URL
                    new_url = re.sub(r'from_date=[^&]*', f'from_date={from_date}', current_url)
                    new_url = re.sub(r'to_date=[^&]*', f'to_date={to_date}', new_url)
                    new_url = re.sub(r'filter_by=[^&]*', 'filter_by=CustomDate', new_url)
                    
                    self.logger.info(f"Navigating to updated URL: {new_url}")
                    await page.goto(new_url, wait_until="load")
                    await asyncio.sleep(20)
                else:
                    self.logger.warning(f"URL does not contain date parameters. Current URL: {current_url}")
                    # Attempt simple UI click to trigger URL change if not present
                    # (This part is speculative but helps if initial drill down didn't add params)
                    # For now, let's just log it.


                await page.screenshot(path="logs/after_date_set.png")

                # 4. Export
                self.logger.info("Triggering Export...")
                found_export = False
                for frame in page.frames:
                    try:
                        clicked = await frame.evaluate('''() => {
                            const btns = Array.from(document.querySelectorAll('button, a'));
                            const exportBtn = btns.find(b => b.getAttribute('aria-label') === 'Export As' || b.textContent.includes('Export As') || b.id === 'export-as-btn' || b.textContent.includes('Export'));
                            if (exportBtn) {
                                exportBtn.click();
                                return true;
                            }
                            return false;
                        }''')
                        if clicked:
                            found_export = True
                            break
                    except: continue

                await asyncio.sleep(5)

                async with page.expect_download(timeout=120000) as download_info:
                    self.logger.info("Searching for XLSX option...")
                    for frame in page.frames:
                        try:
                            clicked = await frame.evaluate('''() => {
                                const items = Array.from(document.querySelectorAll('a, li, span, button, .dropdown-item'));
                                const xlsx = items.find(el => el.textContent.trim().toUpperCase() === 'XLSX' || el.textContent.includes('XLSX'));
                                if (xlsx) {
                                    xlsx.click();
                                    return true;
                                }
                                return false;
                            }''');
                            if clicked: break
                        except: continue
                    
                    await asyncio.sleep(5)
                    
                    # Check for "Export" button in a modal
                    for frame in page.frames:
                        try:
                            await frame.evaluate('''() => {
                                const modal = document.querySelector('.modal-content, .modal-dialog');
                                if (modal) {
                                    const btns = Array.from(modal.querySelectorAll('button'));
                                    const exportBtn = btns.find(b => b.textContent.includes('Export') || b.textContent.includes('Next') || b.textContent.includes('Save'));
                                    if (exportBtn) exportBtn.click();
                                }
                            }''')
                        except: continue
                
                download = await download_info.value
                safe_account_name = account_name.replace(" ", "_").replace("/", "_").lower()
                filename = f"{safe_account_name}_{from_date.replace('-','')}_{to_date.replace('-','')}.xlsx"
                save_path = self.download_dir / filename
                await download.save_as(str(save_path))
                self.logger.info(f"Successfully downloaded: {save_path}")
                return str(save_path)

            except Exception as e:
                self.logger.error(f"Automation failed: {e}")
                await page.screenshot(path="logs/error_fudr.png")
                return None
            finally:
                await context.close()
