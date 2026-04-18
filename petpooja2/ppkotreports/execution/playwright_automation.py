"""
Playwright Automation Module for Petpooja KOT Reports.
Sequential UI interactions on the Billing subdomain.
"""

import os
import sys
import asyncio
import datetime
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

from playwright.async_api import async_playwright, Page, BrowserContext
from execution.logger_helper import LoggerHelper

class PlaywrightAutomation:
    """Headless automation for Custom KOT Reports."""

    def __init__(self, headless: bool = True, settings_path: str = "settings.json") -> None:
        self.headless = headless
        self.settings_path = Path(settings_path)
        self.settings = self._load_settings()
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger
        
        self.username = os.getenv("PETPOOJA_USERNAME")
        self.password = os.getenv("PETPOOJA_PASSWORD")
        
        self.profile_dir = Path(self.settings.get("playwright_profile_dir", "/home/mcsuser/work/rwppdatatransfer/playwrightprofile/"))
        self.download_dir = Path(self.settings.get("download_dir", self.profile_dir / "downloads"))
        
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _load_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists(): return {}
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_download_dir(self):
        """Purge all report files from the download directory."""
        if not self.download_dir.exists(): return
        removed_count = 0
        for file_path in self.download_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in [".csv", ".xlsx"]:
                file_path.unlink()
                removed_count += 1
        if removed_count > 0:
            self.logger.info(f"Purged {removed_count} stale files.")

    async def run(self, target_date: Optional[datetime.date] = None) -> Optional[Path]:
        if target_date is None: target_date = datetime.date.today()
        self.logger.info(f"--- Starting KOT Report Extraction for {target_date} ---")

        async with async_playwright() as p:
            try:
                context = await p.firefox.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                    args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
                    viewport={"width": 1440, "height": 900},
                    accept_downloads=True
                )
            except Exception as e:
                self.logger.error(f"Failed to launch Playwright: {e}")
                return None

            try:
                page = context.pages[0] if context.pages else await context.new_page()

                if not await self._ensure_logged_in(page):
                    await context.close()
                    return None

                raw_outlets = self.settings.get("petpooja_outlet_name", "")
                outlets = [o.strip() for o in raw_outlets.split(",") if o.strip()]
                
                downloaded_count = 0
                for outlet in outlets:
                    if await self._process_single_outlet(page, outlet, target_date):
                        downloaded_count += 1
                        self.logger.info(f"SUCCESS: KOT Report for {outlet}")
                    else:
                        self.logger.warning(f"FAILURE: KOT Report for {outlet}")
                
                await context.close()
                return self.download_dir if downloaded_count > 0 else None

            except Exception as e:
                self.logger.error(f"Critical error: {e}")
                await context.close()
                return None

    async def _ensure_logged_in(self, page: Page) -> bool:
        dashboard_url = "https://billing.petpooja.com/users/dashboard"
        try:
            await page.goto(dashboard_url, wait_until="load", timeout=60000)
            await asyncio.sleep(5)
            if "login" in page.url.lower() or await page.locator("input#UserEmail").count() > 0:
                self.logger.info("Auth required. Logging in...")
                await page.locator("input#UserEmail").fill(self.username)
                await page.locator("button[type='submit']").click()
                await asyncio.sleep(3)
                if await page.locator("input#UserPassword").count() > 0:
                    await page.locator("input#UserPassword").fill(self.password)
                    await page.locator("button[type='submit']").click()
                await page.wait_for_url("**/dashboard*", timeout=60000)
            return True
        except Exception as e:
            self.logger.error(f"Auth check failed: {e}")
            return False

    async def _process_single_outlet(self, page: Page, outlet: str, target_date: datetime.date) -> bool:
        self.logger.info(f"\n>>> KOT REPORT: {outlet}")
        date_str = target_date.strftime("%Y-%m-%d")
        report_url = self.settings.get("petpooja_url")
        
        try:
            # 1. Switch Outlet
            await page.goto("https://billing.petpooja.com/users/dashboard")
            await asyncio.sleep(5)
            await self._close_popups(page)
            await page.locator("#restaurant_dropdown_pad").click(force=True)
            await asyncio.sleep(3)
            
            # Use exact match logic
            await page.evaluate(f'''(target) => {{
                const els = Array.from(document.querySelectorAll('.search_res_name, .restro-title-name'));
                for (let el of els) {{
                    if (el.textContent.trim().toLowerCase() === target.toLowerCase()) {{
                        el.click();
                        return;
                    }}
                }}
            }}''', outlet)
            self.logger.info("Waiting for session sync...")
            await asyncio.sleep(15)

            # 2. Go to Custom Report
            self.logger.info(f"Navigating to Custom Report: {report_url}")
            await page.goto(report_url, wait_until="load", timeout=90000)
            await asyncio.sleep(10)

            # 3. Set Date (Targeting .start_fromdate and .end_todate)
            self.logger.info(f"Setting dates to {date_str}...")
            await page.evaluate(f'''(d) => {{
                const from_el = document.querySelector(".start_fromdate");
                const to_el = document.querySelector(".end_todate");
                if (from_el) {{
                    from_el.value = d + " 05:00:00";
                    from_el.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
                if (to_el) {{
                    to_el.value = d + " 23:59:59";
                    to_el.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}''', date_str)
            await asyncio.sleep(2)

            # 4. Search (Using re_final_search class)
            self.logger.info("Clicking Search...")
            search_btn = page.locator(".re_final_search, button#search, .primary-btn:has-text('Search')").first
            await search_btn.click(force=True)
            self.logger.info("Waiting for report to generate...")
            await asyncio.sleep(20) # Custom reports take time to aggregate

            # 5. Export (Target <span>Excel</span> inside .dt-button)
            self.logger.info("Finding Excel download button...")
            excel_btn = page.locator(".dt-button.buttons-excel, span:has-text('Excel')").first
            if await excel_btn.count() > 0:
                self.logger.info("Triggering download...")
                async with page.expect_download(timeout=120000) as download_info:
                    await excel_btn.click(force=True)
                download = await download_info.value
                filename = f"KOT_{date_str}_{outlet.replace(' ', '_')}.xlsx"
                await download.save_as(str(self.download_dir / filename))
                return True
            
            self.logger.error("Excel button not found.")
            return False

        except Exception as e:
            self.logger.error(f"KOT extraction failed for {outlet}: {e}")
            return False

    async def _close_popups(self, page: Page) -> None:
        try:
            await page.evaluate('''() => {
                const containers = document.querySelectorAll('.fancybox-container, .modal-backdrop, .fancybox-overlay');
                containers.forEach(container => { container.style.display = 'none'; });
            }''')
        except: pass
