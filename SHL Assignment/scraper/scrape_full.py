"""
Comprehensive scraper: combines table scraping (first few pages) with
individual detail page scraping from Wayback Machine CDX index.
"""
import asyncio
import json
import os
import re
import httpx
from bs4 import BeautifulSoup

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catalog.json")
WAYBACK_BASE = "https://web.archive.org/web/20250122211808/https://www.shl.com/solutions/products/product-catalog/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def parse_individual_tests_from_table(html: str) -> list[dict]:
    """Parse Individual Test Solutions from the catalog table HTML."""
    soup = BeautifulSoup(html, "html.parser")
    assessments = []

    tables = soup.find_all("table")
    for table in tables:
        header_row = table.find("tr")
        if not header_row:
            continue
        header_text = header_row.get_text(strip=True)
        if "Individual Test Solutions" not in header_text:
            continue

        rows = table.find_all("tr")[1:]
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

            # Fix wayback URLs
            if "/web/" in href:
                match = re.search(r"/web/\d+/(https?://.*)", href)
                if match:
                    url = match.group(1)
                else:
                    url = href
            elif href.startswith("/"):
                url = f"https://www.shl.com{href}"
            else:
                url = href

            # Parse metadata columns
            remote_testing = False
            adaptive_irt = False
            test_type = ""

            if len(cells) > 1:
                cell_html = str(cells[1])
                remote_testing = "catalogue__circle--fill" in cell_html
            if len(cells) > 2:
                cell_html = str(cells[2])
                adaptive_irt = "catalogue__circle--fill" in cell_html
            if len(cells) > 3:
                test_type = cells[3].get_text(strip=True)

            assessments.append({
                "name": name,
                "url": url,
                "remote_testing": remote_testing,
                "adaptive_irt": adaptive_irt,
                "test_type": test_type,
            })

    return assessments


def parse_detail_page(html: str, url: str) -> dict | None:
    """Parse a single assessment detail page."""
    soup = BeautifulSoup(html, "html.parser")

    # Get the assessment name from h1 or title
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        title = soup.find("title")
        name = title.get_text(strip=True).split("|")[0].strip() if title else ""

    if not name:
        return None

    # Get description
    description = ""
    # Look for main content paragraph
    main = soup.find("main") or soup.find(class_=re.compile(r"content|main"))
    if main:
        paragraphs = main.find_all("p")
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 50:  # Skip short paragraphs
                description = text
                break

    # Look for test type, remote testing, adaptive indicators
    test_type = ""
    remote_testing = False
    adaptive_irt = False

    # Check for metadata in tables or definition lists
    page_text = soup.get_text()
    
    # Test type patterns
    type_patterns = {
        "K": ["knowledge", "technical"],
        "P": ["personality", "questionnaire"],
        "C": ["cognitive", "ability", "reasoning"],
        "B": ["behavioral", "competency", "situational"],
        "S": ["simulation", "skills"],
        "A": ["ability"],
        "E": ["experience"],
    }

    return {
        "name": name,
        "url": url,
        "description": description,
        "test_type": test_type,
        "remote_testing": remote_testing,
        "adaptive_irt": adaptive_irt,
    }


async def get_cdx_urls() -> list[str]:
    """Get all unique assessment detail page URLs from Wayback CDX."""
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        cdx_url = (
            "https://web.archive.org/cdx/search/cdx?"
            "url=www.shl.com/solutions/products/product-catalog/view/*"
            "&output=json&limit=1000&filter=statuscode:200&collapse=urlkey"
        )
        resp = await client.get(cdx_url)
        data = json.loads(resp.text)

        urls = []
        for row in data[1:]:  # Skip header
            original = row[2]
            timestamp = row[1]
            urls.append((original, timestamp))

        return urls


async def scrape_catalog():
    """Main scraping function combining table and detail page approaches."""
    all_assessments = []
    seen_names = set()

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        # Phase 1: Scrape from table pages (we know pages 1-3 work)
        print("=== Phase 1: Scraping from catalog table ===")
        for page_num in range(3):
            start = page_num * 12
            if page_num == 0:
                url = WAYBACK_BASE
            else:
                url = f"{WAYBACK_BASE}?start={start}&type=1"

            print(f"  Page {page_num + 1} (start={start})...")
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    assessments = parse_individual_tests_from_table(resp.text)
                    for a in assessments:
                        if a["name"] not in seen_names:
                            seen_names.add(a["name"])
                            all_assessments.append(a)
                    print(f"    Found {len(assessments)} assessments")
            except Exception as e:
                print(f"    Error: {e}")
            await asyncio.sleep(1)

        # Phase 2: Get all detail page URLs from CDX and scrape them
        print(f"\n=== Phase 2: Finding detail pages from CDX ===")
        cdx_entries = await get_cdx_urls()
        print(f"  Found {len(cdx_entries)} detail page URLs in CDX")

        # Filter out pre-packaged solutions (ones that don't match individual tests)
        pre_packaged_keywords = [
            "solution", "short-form", "manager-solution", "agent-solution",
        ]

        detail_pages_fetched = 0
        for original_url, timestamp in cdx_entries:
            # Skip URLs we already have from table scraping
            # Also skip pre-packaged job solutions
            slug = original_url.split("/view/")[-1].rstrip("/")

            # Build wayback URL
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"

            # Check if we already have this one
            already_have = False
            for a in all_assessments:
                if slug in a.get("url", ""):
                    already_have = True
                    break
            if already_have:
                continue

            # Fetch the detail page
            try:
                resp = await client.get(wayback_url, timeout=15)
                if resp.status_code == 200:
                    result = parse_detail_page(resp.text, original_url)
                    if result and result["name"] and result["name"] not in seen_names:
                        seen_names.add(result["name"])
                        all_assessments.append(result)
                        detail_pages_fetched += 1
                        if detail_pages_fetched % 10 == 0:
                            print(f"    Fetched {detail_pages_fetched} detail pages...")
            except Exception:
                pass
            await asyncio.sleep(0.5)

        print(f"  Fetched {detail_pages_fetched} new assessments from detail pages")

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_assessments, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"Total unique assessments: {len(all_assessments)}")
    print(f"Saved to: {OUTPUT_PATH}")

    # Summary by test type
    type_counts = {}
    for a in all_assessments:
        tt = a.get("test_type", "unknown")
        if not tt:
            tt = "unknown"
        type_counts[tt] = type_counts.get(tt, 0) + 1
    print(f"\nTest type distribution:")
    for t, count in sorted(type_counts.items()):
        print(f"  {t}: {count}")

    return all_assessments


if __name__ == "__main__":
    asyncio.run(scrape_catalog())
