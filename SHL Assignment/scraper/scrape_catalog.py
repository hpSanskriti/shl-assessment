"""
Scraper for SHL Product Catalog using httpx + BeautifulSoup.
The catalog page at /solutions/products/product-catalog/ returns server-rendered HTML
with a table of Individual Test Solutions. Direct HTTP access works (Playwright redirects due to JS).
"""
import asyncio
import json
import os
import re
import httpx
from bs4 import BeautifulSoup

CATALOG_BASE = "https://www.shl.com/solutions/products/product-catalog/"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catalog.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def fetch_page(client: httpx.AsyncClient, url: str) -> str:
    """Fetch a page and return HTML content."""
    resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
    return resp.text


def parse_catalog_page(html: str) -> list[dict]:
    """Parse assessments from a catalog page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    assessments = []

    # Find the catalog table
    table = soup.find("table")
    if not table:
        # Try to find links to individual catalog items
        links = soup.find_all("a", href=re.compile(r"/solutions/products/product-catalog/"))
        for link in links:
            name = link.get_text(strip=True)
            href = link.get("href", "")
            if name and href and href != CATALOG_BASE and "type=" not in href:
                url = href if href.startswith("http") else f"https://www.shl.com{href}"
                assessments.append({"name": name, "url": url})
        return assessments

    # Parse table rows
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        first_cell = cells[0]
        link = first_cell.find("a")
        if not link:
            continue

        name = link.get_text(strip=True)
        href = link.get("href", "")
        if not name:
            continue

        url = href if href.startswith("http") else f"https://www.shl.com{href}"

        remote_testing = ""
        adaptive_irt = ""
        test_type = ""
        duration = ""

        for i, cell in enumerate(cells[1:], 1):
            has_filled = cell.find(class_=re.compile(r"catalogue__circle--fill|icon.*check|yes"))
            cell_text = cell.get_text(strip=True)

            if i == 1:
                remote_testing = "Yes" if has_filled else cell_text
            elif i == 2:
                adaptive_irt = "Yes" if has_filled else cell_text
            elif i == 3:
                test_type = cell_text
            elif i == 4:
                duration = cell_text

        assessments.append({
            "name": name,
            "url": url,
            "remote_testing": remote_testing,
            "adaptive_irt": adaptive_irt,
            "test_type": test_type,
            "duration": duration,
        })

    return assessments


def find_next_page_url(html: str, current_page: int) -> str | None:
    """Find the URL for the next page of results."""
    soup = BeautifulSoup(html, "html.parser")
    
    # Look for pagination links
    next_link = soup.find("a", class_=re.compile(r"next"))
    if next_link:
        href = next_link.get("href", "")
        if href:
            return href if href.startswith("http") else f"https://www.shl.com{href}"

    # Look for numbered page links
    next_page = current_page + 1
    next_link = soup.find("a", href=re.compile(rf"[?&]page={next_page}"))
    if next_link:
        href = next_link.get("href", "")
        return href if href.startswith("http") else f"https://www.shl.com{href}"

    return None


async def scrape_catalog():
    """Scrape the full SHL Individual Test Solutions catalog."""
    all_assessments = []

    async with httpx.AsyncClient() as client:
        # Start with the catalog page
        start_url = CATALOG_BASE
        print(f"Fetching: {start_url}")
        html = await fetch_page(client, start_url)

        # Save raw HTML for debugging
        debug_path = os.path.join(os.path.dirname(OUTPUT_PATH), "catalog_raw.html")
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Saved raw HTML ({len(html)} bytes)")

        assessments = parse_catalog_page(html)
        if assessments:
            print(f"  Found {len(assessments)} assessments on page 1")
            all_assessments.extend(assessments)
        else:
            print("  No assessments found on main page. Trying with type filter...")
            # Try type=1 for Individual Test Solutions
            html = await fetch_page(client, f"{CATALOG_BASE}?type=1")
            assessments = parse_catalog_page(html)
            if assessments:
                print(f"  Found {len(assessments)} assessments with type=1")
                all_assessments.extend(assessments)

        # Paginate through remaining pages
        page_num = 1
        while True:
            next_url = find_next_page_url(html, page_num)
            if next_url:
                print(f"  Fetching next page: {next_url}")
                html = await fetch_page(client, next_url)
                new_assessments = parse_catalog_page(html)
                if new_assessments:
                    print(f"  Page {page_num + 1}: {len(new_assessments)} assessments")
                    all_assessments.extend(new_assessments)
                    page_num += 1
                else:
                    break
            else:
                # Try incrementing page number manually
                page_num += 1
                guess_url = f"{CATALOG_BASE}?type=1&page={page_num}"
                html = await fetch_page(client, guess_url)
                new_assessments = parse_catalog_page(html)
                if new_assessments:
                    print(f"  Page {page_num}: {len(new_assessments)} assessments (guessed URL)")
                    all_assessments.extend(new_assessments)
                else:
                    break

            # Safety limit
            if page_num > 20:
                break

    # Deduplicate
    seen = set()
    unique = []
    for a in all_assessments:
        key = a.get("url", a.get("name"))
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    # Save
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"Total unique assessments: {len(unique)}")
    print(f"Saved to: {OUTPUT_PATH}")
    for a in unique[:10]:
        print(f"  - {a['name']}")

    return unique


if __name__ == "__main__":
    asyncio.run(scrape_catalog())
