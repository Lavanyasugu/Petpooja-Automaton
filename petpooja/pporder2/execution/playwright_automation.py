"""
Playwright Automation Module for Petpooja Stock Summary.

Handles headless browser interactions to download Stock Summary reports
from inventory.petpooja.com.
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
    """Headless automation for Petpooja Stock Summary."""

    def __init__(self, headless: bool = True, settings_path: str = "settings.json") -> None:
        """Initialize settings and logger."""
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
        """Load settings from JSON."""
        if not self.settings_path.exists():
            return {}
        with open(self.settings_path, "r", encoding="utf-8") as f:
            return json.load(f)

    async def run(self, target_date: Optional[datetime.date] = None) -> Optional[Path]:
        """Execute the automation for all configured outlets."""
        if target_date is None:
            target_date = datetime.date.today()

        self.logger.info(f"Starting Inventory automation for {target_date}")

        async with async_playwright() as p:
            try:
                context = await p.firefox.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                    args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
                    viewport={"width": 1280, "height": 720},
                    accept_downloads=True
                )
            except Exception as e:
                self.logger.error(f"Failed to launch Playwright: {e}")
                return None

            try:
                page = context.pages[0] if context.pages else await context.new_page()

                # 1. Login Flow
                if not await self._ensure_logged_in(page):
                    await context.close()
                    return None

                # 2. Process Outlets (8 outlets loop)
                raw_outlets = self.settings.get("petpooja_outlet_name", "")
                outlets = [o.strip() for o in raw_outlets.split(",") if o.strip()]
                
                downloaded_count = 0
                for outlet in outlets:
                    if await self._process_single_outlet(page, outlet, target_date):
                        downloaded_count += 1
                    else:
                        self.logger.warning(f"Failed to download for {outlet}")
                
                await context.close()
                
                if downloaded_count > 0:
                    self.logger.info(f"Successfully downloaded {downloaded_count} reports.")
                    return self.download_dir
                return None

            except Exception as e:
                self.logger.error(f"Unhandled exception in run: {e}")
                await context.close()
                return None

    async def _ensure_logged_in(self, page: Page) -> bool:
        """Handle login via dashboard and ensure we are authenticated."""
        dashboard_url = "https://billing.petpooja.com/"
        
        self.logger.info(f"Navigating to dashboard: {dashboard_url}")
        try:
            await page.goto(dashboard_url, wait_until="load", timeout=60000)
            await asyncio.sleep(3)
        except Exception as e:
            self.logger.warning(f"Initial navigation took too long: {e}")

        # Detect redirected login screen
        if "login" in page.url.lower() or await page.locator("input#UserEmail").count() > 0:
            self.logger.info("Login required for Petpooja.")
            if not self.username or not self.password:
                self.logger.error("No credentials available in .env.")
                return False
            
            try:
                await page.locator("input#UserEmail").fill(self.username)
                await page.locator("button[type='submit']").click()
                await asyncio.sleep(2)
                await page.locator("input#UserPassword").fill(self.password)
                await page.locator("button[type='submit']").click()
                
                await page.wait_for_url("**/dashboard*", timeout=60000)
                self.logger.info("Successfully logged in.")
                await self._close_popups(page)
            except Exception as e:
                self.logger.error(f"Login attempt failed: {e}")
                return False
        
        return True

    async def _process_single_outlet(self, page: Page, outlet: str, target_date: datetime.date) -> bool:
        """Select outlet on dashboard and trigger export on report page."""
        self.logger.info(f"--- Processing Outlet: {outlet} ---")
        date_str = target_date.strftime("%Y-%m-%d")
        dashboard_url = "https://billing.petpooja.com/"
        target_url = self.settings.get("petpooja_url", "https://inventory.petpooja.com/inventories/daily_report/")
        
        try:
            # 1. Switch Outlet context on Dashboard
            await page.goto(dashboard_url, wait_until="load")
            await asyncio.sleep(2)
            await self._close_popups(page)

            current_outlet_sel = "#restaurant_dropdown_pad"
            await page.wait_for_selector(current_outlet_sel, timeout=15000)
            current_text = (await page.locator(current_outlet_sel).inner_text()).strip()
            
            if outlet.lower() in current_text.lower():
                self.logger.info(f"Already on correct outlet: {current_text}")
            else:
                self.logger.info(f"Switching outlet from '{current_text}' to '{outlet}'")
                await page.locator(current_outlet_sel).click(force=True)
                await asyncio.sleep(2)
                
                # Search Box inside Modal
                search_input = page.locator("#restro-select-pop-div input[type='text'], #restro-select-pop-div input[placeholder*='Search']").first
                if await search_input.count() > 0:
                    await search_input.fill("")
                    await asyncio.sleep(0.5)
                    await search_input.type(outlet, delay=50)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(2)

                # Enhanced Selection JS (Fuzzy Match)
                found = await page.evaluate(f'''(target) => {{
                    const normalizedTarget = target.toLowerCase().replace(/\\s+/g, ' ').trim();
                    const popup = document.querySelector('#restro-select-pop-div');
                    if (!popup) return false;

                    const titleEls = Array.from(popup.querySelectorAll('.restro-title-name, .restro-title, a, span, li'));
                    for (let el of titleEls) {{
                        const text = el.textContent.toLowerCase().replace(/\\s+/g, ' ').trim();
                        if (text.includes(normalizedTarget) || normalizedTarget.includes(text)) {{
                            const clickable = el.closest('a') || el.closest('li') || el;
                            clickable.click();
                            return true;
                        }}
                    }}
                    return false;
                }}''', outlet)

                if found:
                    self.logger.info(f"Selected outlet via fuzzy match: {outlet}")
                    await page.wait_for_load_state("load")
                    await asyncio.sleep(5)
                else:
                    self.logger.warning(f"Could not find outlet '{outlet}' in the popup.")

            # 2. Navigate to Inventory Report
            self.logger.info(f"Navigating to report URL: {target_url}")
            await page.goto(target_url, wait_until="load")
            await asyncio.sleep(3)

            # 3. Set Date
            await page.evaluate(f'''(d) => {{
                const el = document.querySelector("#report_date, input[name='date']");
                if (el) {{
                    el.value = d;
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            }}''', date_str)
            
            # 4. Search
            search_btn = page.locator("button#search_report, button:has-text('Search')").first
            await search_btn.click()
            self.logger.info(f"Clicked Search for {outlet}")
            await asyncio.sleep(5)
            
            # 5. Export Process (Two-Step: Export -> Export All)
            self.logger.info(f"Initiating export for {outlet}...")
            
            try:
                # Step A: Click the main "Export" button/dropdown trigger
                export_trigger = page.locator("a:has-text('Export'), button:has-text('Export'), .btn:has-text('Export')").filter(has_text="Export").first
                
                if await export_trigger.count() > 0:
                    self.logger.info("Clicking main Export dropdown trigger...")
                    await export_trigger.click(force=True)
                    await asyncio.sleep(2) # Wait for dropdown to appear
                    
                    # Step B: Click "Export All" from the revealed menu
                    export_all_btn = page.locator("a:has-text('Export All'), li:has-text('Export All'), span:has-text('Export All')").first
                    
                    if await export_all_btn.count() > 0:
                        self.logger.info("Found 'Export All' button. Triggering download...")
                        async with page.expect_download(timeout=120000) as download_info:
                            await export_all_btn.click(force=True)
                        
                        download = await download_info.value
                        filename = f"{date_str}_{outlet.replace(' ', '_')}_report.xlsx"
                        save_path = self.download_dir / filename
                        await download.save_as(str(save_path))
                        self.logger.info(f"File saved: {filename}")
                        return True
                    else:
                        self.logger.warning("'Export All' option not found in dropdown.")
                else:
                    self.logger.error(f"Main 'Export' button not found for {outlet}.")

            except Exception as dl_err:
                self.logger.error(f"Export failed for {outlet}: {dl_err}")
            
            return False

        except Exception as e:
            self.logger.error(f"Error processing {outlet}: {e}")
            return False

    async def _close_popups(self, page: Page) -> None:
        """Close common Petpooja overlay modals."""
        try:
            close_selectors = [".fancybox-close-small", ".fancybox-button--close", "button[data-fancybox-close]"]
            for selector in close_selectors:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(force=True)
                    await asyncio.sleep(1)
            
            # Force hide via JS
            await page.evaluate('''() => {
                const containers = document.querySelectorAll('.fancybox-container.fancybox-is-open, #fancybox-container-1');
                containers.forEach(container => { container.style.display = 'none'; });
            }''')
        except:
            pass
