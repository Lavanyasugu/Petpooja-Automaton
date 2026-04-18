"""
Petpooja Playwright Automation for Itemwise Order Summary.

This module provides browser automation to download Itemwise Order Summary reports.
"""

import os
import sys
import json
import asyncio
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from playwright.async_api import async_playwright, Page, BrowserContext
from execution.logger_helper import LoggerHelper
from execution.file_downloader import download_file


class PlaywrightAutomation:
    """
    Playwright-based browser automation for Petpooja Itemwise reports.
    """

    def __init__(self, settings_path: str = "settings.json", headless: bool = True):
        self.logger_helper = LoggerHelper()
        self.logger = self.logger_helper.logger

        self.headless = headless
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)

        self.username = os.getenv("PETPOOJA_USERNAME")
        self.password = os.getenv("PETPOOJA_PASSWORD")

        self.profile_dir = Path(os.getenv("PLAYWRIGHT_PROFILE_DIR", self.settings.get("playwright_profile_dir", "/home/admin/petpooja2/playwrightprofile/")))
        self.download_dir = Path(self.settings.get("download_dir", self.profile_dir / "downloads"))
        
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Initialized directories: Profile={self.profile_dir}, Download={self.download_dir}")

    async def run(self, target_date: Optional[datetime.date] = None) -> Optional[Path]:
        if target_date is None:
            target_date = datetime.date.today() - datetime.timedelta(days=1)

        self.logger.info(f"Starting Playwright automation for Itemwise Report on {target_date}")

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
                    self.logger.error("Failed to authenticate.")
                    await page.screenshot(path="page_debug.png")
                    with open("page_debug.html", "w") as f:
                        f.write(await page.content())
                    return None

                report_url = await self._trigger_and_get_download_link(page, target_date)
                if not report_url:
                    self.logger.error(f"Failed to extract download link for {target_date}")
                    await page.screenshot(path="page_debug.png")
                    with open("page_debug.html", "w") as f:
                        f.write(await page.content())
                    return None

                target_filename = f"{target_date}_itemwise_report.csv"
                target_path = self.download_dir / target_filename
                
                if target_path.exists():
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    target_path = self.download_dir / f"{target_date}_{timestamp}_itemwise_report.csv"

                self.logger.info(f"Downloading report to {target_path}")
                success = download_file(report_url, str(target_path))

                if success and target_path.exists() and target_path.stat().st_size > 0:
                    self.logger.info(f"Download completed successfully: {target_path.name}")
                    await self._clear_report_for_date(page, target_date)
                    return target_path
                else:
                    self.logger.error("File download failed.")
                    return None

            except Exception as e:
                self.logger.error(f"Unhandled exception in Playwright: {e}")
                await page.screenshot(path="page_debug.png")
                return None
            finally:
                await context.close()

    async def _ensure_logged_in(self, page: Page) -> bool:
        report_url = self.settings.get("petpooja_url", "https://billing.petpooja.com/reports/order_summary_item")
        self.logger.info(f"Navigating to {report_url}")
        
        await page.goto(report_url, wait_until="load", timeout=60000)
        await asyncio.sleep(5)

        if "login" not in page.url.lower() and await page.locator("input#UserEmail").count() == 0:
            self.logger.info("Already authenticated.")
            return True

        self.logger.info("Auth required. Logging in...")
        if not self.username or not self.password:
            self.logger.error("Missing credentials.")
            return False

        try:
            await page.locator("input#UserEmail").fill(self.username)
            await page.locator("button[type='submit']").click()
            await asyncio.sleep(2)
            await page.locator("input#UserPassword").fill(self.password)
            await page.locator("button[type='submit']").click()
            await page.wait_for_url("**/dashboard*", timeout=30000)
            
            await page.goto(report_url, wait_until="load")
            return True
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return False

    async def _trigger_and_get_download_link(self, page: Page, target_date: datetime.date) -> Optional[str]:
        date_str = target_date.strftime("%Y-%m-%d")
        self.logger.info(f"Setting dates to {date_str} and triggering export...")

        download_url = None
        
        async def handle_response(response):
            nonlocal download_url
            if "order_summary_item_ajax" in response.url and response.status == 200:
                try:
                    data = await response.json()
                    directories = data.get("directory_path", "").replace("\\/", "/")
                    files = data.get("file_name", [])
                    date_range = f"{date_str} to {date_str}"
                    self.logger.info(f"AJAX response received. Found {len(files)} files.")
                    for file_info in files:
                        if file_info.get("date") == date_range:
                            download_url = directories + file_info["name"]
                            self.logger.info(f"Matching download link found: {download_url}")
                            break
                except Exception as e:
                    self.logger.debug(f"Error parsing AJAX response: {e}")
                    
        page.on("response", handle_response)

        # Inject Date with more events to be sure
        await page.evaluate(f"""
            (() => {{
                const f = document.querySelector('input[name="data[Order][startdate]"]');
                const t = document.querySelector('input[name="data[Order][enddate]"]');
                if(f) {{ 
                    f.value="{date_str}"; 
                    f.dispatchEvent(new Event('input', {{bubbles:true}}));
                    f.dispatchEvent(new Event('change', {{bubbles:true}})); 
                    f.dispatchEvent(new Event('blur', {{bubbles:true}}));
                }}
                if(t) {{ 
                    t.value="{date_str}"; 
                    t.dispatchEvent(new Event('input', {{bubbles:true}}));
                    t.dispatchEvent(new Event('change', {{bubbles:true}})); 
                    t.dispatchEvent(new Event('blur', {{bubbles:true}}));
                }}
            }})()
        """)
        await asyncio.sleep(2)

        # Search/Export
        # Targeting the specific ID found in HTML
        export_btn = page.locator("#order_searc1h, #order_search, button:has-text('Export')").first
        if await export_btn.count() > 0:
            self.logger.info("Clicking export button...")
            await export_btn.click(force=True)
        else:
            self.logger.error("Export button not found!")
            return None

        # Wait for the download link to appear (either via AJAX or DOM)
        for i in range(45):
            if download_url: return download_url
            
            # Check for success message in DOM which might indicate it's ready but AJAX was missed
            if i % 5 == 0:
                self.logger.info(f"Waiting for download link... ({i}s)")
                
            await asyncio.sleep(1)

        # DOM Fallback
        self.logger.info("Attempting DOM fallback for download link...")
        date_search = target_date.strftime("%d-%m-%Y")
        dom_url = await page.evaluate(f'''
            (() => {{
                const rows = document.querySelectorAll('#reports_data tr');
                for (const row of rows) {{
                    if (row.textContent.includes("{date_search}")) {{
                        const link = row.querySelector('a[href*="s3"]');
                        if (link) return link.href;
                    }}
                }}
                return null;
            }})()
        ''')
        return dom_url

    async def _clear_report_for_date(self, page: Page, target_date: datetime.date) -> None:
        date_range = f"{target_date} to {target_date}"
        try:
            await page.evaluate(f'''
                (() => {{
                    const rows = document.querySelectorAll('#reports_data tr');
                    for (const row of rows) {{
                        if (row.textContent.includes("{date_range}")) {{
                            const btn = row.querySelector('input.clear_report');
                            if (btn) btn.click();
                        }}
                    }}
                }})()
            ''')
        except: pass
