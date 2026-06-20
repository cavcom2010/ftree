import asyncio
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        # Login
        await page.goto(f"{BASE}/accounts/login/")
        await page.fill("input[name='username']", "demo")
        await page.fill("input[name='password']", "demodemo")
        await page.click(".auth-form button[type='submit']")
        await page.wait_for_load_state("networkidle")

        # Go to tree
        await page.goto(f"{BASE}/tree/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="screenshots/tree_admin_desktop.png", full_page=True)

        # Empty-state user
        await page.goto(f"{BASE}/accounts/login/")
        await page.fill("input[name='username']", "testempty")
        await page.fill("input[name='password']", "testempty")
        await page.click(".auth-form button[type='submit']")
        await page.wait_for_load_state("networkidle")
        await page.goto(f"{BASE}/tree/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="screenshots/tree_setup_desktop.png", full_page=True)

        # Mobile admin
        mobile = await browser.new_context(viewport={"width": 390, "height": 844})
        mpage = await mobile.new_page()
        await mpage.goto(f"{BASE}/accounts/login/")
        await mpage.fill("input[name='username']", "demo")
        await mpage.fill("input[name='password']", "demodemo")
        await mpage.click(".auth-form button[type='submit']")
        await mpage.wait_for_load_state("networkidle")
        await mpage.goto(f"{BASE}/tree/")
        await mpage.wait_for_load_state("networkidle")
        await mpage.screenshot(path="screenshots/tree_admin_mobile.png", full_page=True)

        # Mobile empty-state
        mpage2 = await mobile.new_page()
        await mpage2.goto(f"{BASE}/accounts/login/")
        await mpage2.fill("input[name='username']", "testempty")
        await mpage2.fill("input[name='password']", "testempty")
        await mpage2.click(".auth-form button[type='submit']")
        await mpage2.wait_for_load_state("networkidle")
        await mpage2.goto(f"{BASE}/tree/")
        await mpage2.wait_for_load_state("networkidle")
        await mpage2.screenshot(path="screenshots/tree_setup_mobile.png", full_page=True)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
