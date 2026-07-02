import httpx
import asyncio
from bs4 import BeautifulSoup

async def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        url = "https://www.shl.com/solutions/products/product-catalog/?type=1"
        resp = await client.get(url, timeout=30)
        print(f"Final URL: {resp.url}")
        print(f"Status: {resp.status_code}")
        print(f"Content length: {len(resp.text)} bytes")

        text = resp.text
        has_table = "<table" in text.lower()
        print(f"Has table: {has_table}")

        if has_table:
            start = text.lower().find("<table")
            print(f"Table found at pos {start}")
            print(text[start:start+2000])
        else:
            soup = BeautifulSoup(text, "html.parser")
            title = soup.find("title")
            print(f"Title: {title.get_text() if title else 'N/A'}")

            # Look for catalogue-specific elements
            for el in soup.find_all(class_=lambda c: c and "catalogue" in c.lower()):
                classes = " ".join(el.get("class", []))
                content = el.get_text(strip=True)[:100]
                print(f"  <{el.name} class='{classes}'> {content}")

            # Look for any divs/sections with product data
            for el in soup.find_all(class_=lambda c: c and ("product" in c.lower() or "catalog" in c.lower())):
                classes = " ".join(el.get("class", []))
                content = el.get_text(strip=True)[:80]
                print(f"  <{el.name} class='{classes}'> {content}")

            # Save for inspection
            with open("data/catalog_type1.html", "w", encoding="utf-8") as f:
                f.write(text)
            print("Saved to data/catalog_type1.html")

asyncio.run(main())
