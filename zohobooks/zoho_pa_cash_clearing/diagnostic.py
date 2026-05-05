
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    with open("settings.json", "r") as f:
        settings = json.load(f)
    
    async with async_playwright() as p:
        context = await p.firefox.launch_persistent_context(
            user_data_dir=settings['playwright_profile_dir'],
            headless=True
        )
        page = await context.new_page()
        print(f"Navigating to {settings['url']}...")
        await page.goto(settings['url'], wait_until="load")
        await asyncio.sleep(20)
        
        # Check all frames
        print(f"Total frames: {len(page.frames)}")
        for i, frame in enumerate(page.frames):
            print(f"Frame {i}: {frame.name} | {frame.url[:100]}")
            # Try to find 'Fudr Clearing Account' in this frame
            links = await frame.evaluate('''() => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.textContent.trim(),
                    href: a.href
                })).filter(a => a.text.includes('Fudr Clearing Account') || a.text.includes('Clearing'));
            }''')
            if links:
                print(f"Found links in Frame {i}: {links}")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
