"""Use Playwright to intercept XHR/fetch calls that load catalog data."""
import asyncio
import json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Non-headless to avoid bot detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()

        # Collect all API responses
        api_responses = []

        async def handle_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")
            if "json" in content_type or "api" in url or "catalog" in url.lower():
                try:
                    body = await response.text()
                    api_responses.append({
                        "url": url,
                        "status": response.status,
                        "content_type": content_type,
                        "body_length": len(body),
                        "body_preview": body[:500] if len(body) < 5000 else body[:1000],
                    })
                except:
                    pass

        page.on("response", handle_response)

        # Navigate to the products page first
        print("Loading SHL homepage...")
        await page.goto("https://www.shl.com/", wait_until="networkidle", timeout=60000)

        # Accept cookies
        try:
            btn = page.locator("#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll")
            if await btn.is_visible(timeout=5000):
                await btn.click()
                await page.wait_for_timeout(1000)
                print("Cookies accepted")
        except:
            pass

        # Navigate to product catalog
        print("Navigating to product catalog...")
        await page.goto("https://www.shl.com/solutions/products/product-catalog/", 
                       wait_until="networkidle", timeout=60000)
        print(f"Current URL: {page.url}")
        
        # Wait and scroll to trigger lazy loading
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(3000)

        # Check if there's a catalog section that needs to be triggered
        # Look for any elements that might be a catalog filter or tab
        print(f"\nPage URL after load: {page.url}")
        
        # Take screenshot
        await page.screenshot(path="data/catalog_intercept.png")
        
        # Print all intercepted API calls
        print(f"\nIntercepted {len(api_responses)} JSON/API responses:")
        for r in api_responses:
            print(f"  [{r['status']}] {r['url'][:100]}")
            if r["body_length"] > 100:
                print(f"       Type: {r['content_type']}, Size: {r['body_length']}")
                print(f"       Preview: {r['body_preview'][:200]}")
            print()

        # Also check the page content for any table/catalog elements
        tables = await page.locator("table").count()
        print(f"Tables on page: {tables}")
        
        # Check for any elements with 'catalog' or 'catalogue' in class/id
        catalog_els = await page.locator("[class*='catalogue'], [class*='catalog'], [id*='catalog']").count()
        print(f"Catalog elements: {catalog_els}")

        if catalog_els > 0:
            els = await page.locator("[class*='catalogue'], [class*='catalog']").all()
            for el in els[:10]:
                tag = await el.evaluate("el => el.tagName")
                classes = await el.get_attribute("class")
                text = (await el.text_content() or "")[:100]
                print(f"  <{tag} class='{classes}'> {text}")

        await browser.close()

        # Save all API responses for analysis
        with open("data/api_responses.json", "w", encoding="utf-8") as f:
            json.dump(api_responses, f, indent=2)
        print(f"\nSaved {len(api_responses)} API responses to data/api_responses.json")

asyncio.run(main())
