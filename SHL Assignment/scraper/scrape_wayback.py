"""
Scrape SHL Product Catalog from Wayback Machine archive.
The live site no longer serves the catalog page, but the archived version has the data.
We scrape Individual Test Solutions only (not Pre-packaged Job Solutions).
"""
import asyncio
import json
import os
import re
import httpx
from bs4 import BeautifulSoup

WAYBACK_BASE = "https://web.archive.org/web/20250122211808/https://www.shl.com/solutions/products/product-catalog/"
OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catalog.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def parse_individual_tests(html: str) -> list[dict]:
    """Parse Individual Test Solutions from the catalog HTML."""
    soup = BeautifulSoup(html, "html.parser")
    assessments = []

    # Find all tables on the page
    tables = soup.find_all("table")

    for table in tables:
        # Check if this is the Individual Test Solutions table
        header_row = table.find("tr")
        if not header_row:
            continue
        header_text = header_row.get_text(strip=True)
        if "Individual Test Solutions" not in header_text:
            continue

        # Parse rows (skip header)
        rows = table.find_all("tr")[1:]
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # First cell: name + link
            first_cell = cells[0]
            link = first_cell.find("a")
            if not link:
                continue

            name = link.get_text(strip=True)
            href = link.get("href", "")
            if not name:
                continue

            # Fix wayback machine URLs - extract the original URL
            if "/web/" in href:
                # Extract original URL from wayback URL
                match = re.search(r"/web/\d+/(https?://.*)", href)
                if match:
                    url = match.group(1)
                else:
                    url = href
            elif href.startswith("/"):
                url = f"https://www.shl.com{href}"
            elif href.startswith("http"):
                url = href
            else:
                url = f"https://www.shl.com/{href}"

            # Second cell: Remote Testing (check for filled circle icon)
            remote_testing = False
            if len(cells) > 1:
                has_fill = cells[1].find(class_=re.compile(r"fill|check|yes"))
                icon_span = cells[1].find("span")
                if has_fill:
                    remote_testing = True
                elif icon_span and "catalogue__circle--fill" in " ".join(icon_span.get("class", [])):
                    remote_testing = True
                # Also check for any dash/circle indicators
                cell_html = str(cells[1])
                if "circle--fill" in cell_html or "✓" in cell_html:
                    remote_testing = True

            # Third cell: Adaptive/IRT
            adaptive_irt = False
            if len(cells) > 2:
                has_fill = cells[2].find(class_=re.compile(r"fill|check|yes"))
                icon_span = cells[2].find("span")
                if has_fill:
                    adaptive_irt = True
                elif icon_span and "catalogue__circle--fill" in " ".join(icon_span.get("class", [])):
                    adaptive_irt = True
                cell_html = str(cells[2])
                if "circle--fill" in cell_html or "✓" in cell_html:
                    adaptive_irt = True

            # Fourth cell: Test Type (letter codes like K, P, C, A, B, S, E)
            test_type = ""
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


async def scrape_catalog():
    """Scrape all pages of the SHL Individual Test Solutions catalog from Wayback Machine."""
    all_assessments = []
    
    # The catalog uses: ?start=<offset>&type=1 for Individual Test Solutions
    # Each page shows 12 items. Total pages for type=1: 32 (last page start=372)
    # Page 1 (start=0) must use the base URL without type param (Wayback quirk)
    # Subsequent pages use ?start=N&type=1
    WAYBACK_PREFIX = "https://web.archive.org/web/20250122211808/https://www.shl.com/solutions/products/product-catalog/"

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        page_num = 0
        max_start = 384  # 32 pages * 12 items

        while page_num * 12 <= max_start:
            start = page_num * 12
            if page_num == 0:
                # First page: use base URL (both tables present, we filter)
                url = WAYBACK_PREFIX
            else:
                url = f"{WAYBACK_PREFIX}?start={start}&type=1"

            print(f"Page {page_num + 1} (start={start}): fetching...")

            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    print(f"  Got status {resp.status_code}, stopping.")
                    break
            except Exception as e:
                print(f"  Error: {e}, retrying...")
                await asyncio.sleep(3)
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        break
                except:
                    print(f"  Retry failed, stopping.")
                    break

            assessments = parse_individual_tests(resp.text)

            if not assessments:
                print(f"  No Individual Test Solutions found, stopping.")
                break

            print(f"  Found {len(assessments)} assessments")
            all_assessments.extend(assessments)
            page_num += 1
            
            # Be respectful to web.archive.org
            await asyncio.sleep(1.5)

    # Deduplicate by name (URLs from wayback may vary)
    seen = set()
    unique = []
    for a in all_assessments:
        if a["name"] not in seen:
            seen.add(a["name"])
            unique.append(a)

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"Total unique Individual Test Solutions: {len(unique)}")
    print(f"Saved to: {OUTPUT_PATH}")
    
    # Print summary by test type
    type_counts = {}
    for a in unique:
        for t in a.get("test_type", ""):
            type_counts[t] = type_counts.get(t, 0) + 1
    print(f"\nTest type distribution:")
    for t, count in sorted(type_counts.items()):
        print(f"  {t}: {count}")

    return unique


if __name__ == "__main__":
    asyncio.run(scrape_catalog())
