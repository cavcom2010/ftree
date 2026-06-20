import asyncio
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
URL = f"{BASE}/tree/?family=cavcom2010-family-tree"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Desktop
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto(f"{BASE}/accounts/login/")
        await page.fill("input[name='username']", "ftree-admin")
        await page.fill("input[name='password']", "adminadmin")
        await page.click(".auth-form button[type='submit']")
        await page.wait_for_url("**/")
        await page.goto(URL)
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="screenshots/tree_switcher_desktop.png", full_page=True)

        # Mobile
        mobile = await browser.new_context(viewport={"width": 390, "height": 844})
        mpage = await mobile.new_page()
        await mpage.goto(f"{BASE}/accounts/login/")
        await mpage.fill("input[name='username']", "demo")
        await mpage.fill("input[name='password']", "demodemo")
        await mpage.click(".auth-form button[type='submit']")
        await mpage.wait_for_url("**/")
        await mpage.goto(URL)
        await mpage.wait_for_load_state("networkidle")
        await mpage.screenshot(path="screenshots/tree_switcher_mobile.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
