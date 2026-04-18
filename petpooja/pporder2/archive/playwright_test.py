import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    profile_dir = Path("/home/mcsuser/work/rwppdatatransfer/playwrightprofile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting Playwright Firefox with persistent session...")
    print(f"Persistence directory: {profile_dir.absolute()}")

    async with async_playwright() as p:
        # Launch visible (headless=False) persistent context
        context = await p.firefox.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False, # We want to see the UI
            viewport={"width": 1280, "height": 720}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to Petpooja...")
        await page.goto("https://billing.petpooja.com/")
        
        print("Browser opened. Current URL:", page.url)
        print("You can now perform manual actions (like login).")
        print("The session will be saved automatically to /home/mcsuser/work/rwppdatatransfer/playwrightprofile.")
        print("\nPress Ctrl+C in this terminal to close the browser and exit.")

        try:
            # Keep browser open indefinitely until user interrupts
            while True:
                await asyncio.sleep(1)
                # If user closes the browser window manually, exit the script
                if len(context.pages) == 0:
                    print("\nAll pages closed. Exiting...")
                    break
        except KeyboardInterrupt:
            print("\nClosing browser gracefully...")
        finally:
            await context.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass