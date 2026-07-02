"""
Fast catalog builder: Uses CDX API to find all catalog entries,
fetches them in batches, extracts metadata.
"""
import asyncio
import json
import os
import re
import httpx
from bs4 import BeautifulSoup

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catalog.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

# Pre-packaged Job Solutions slugs (to exclude)
JOB_SOLUTION_PATTERNS = [
    "solution", "short-form", "-sf",
]


async def get_all_detail_urls() -> list[tuple[str, str]]:
    """Get all catalog detail page URLs and timestamps from CDX."""
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        cdx_url = (
            "https://web.archive.org/cdx/search/cdx?"
            "url=www.shl.com/solutions/products/product-catalog/view/*"
            "&output=json&limit=2000&filter=statuscode:200&collapse=urlkey"
        )
        resp = await client.get(cdx_url)
        data = json.loads(resp.text)

        results = []
        for row in data[1:]:
            original = row[2]
            timestamp = row[1]
            results.append((original, timestamp))

        return results


async def fetch_detail_page(client: httpx.AsyncClient, url: str, timestamp: str) -> dict | None:
    """Fetch and parse a single detail page from Wayback."""
    wayback_url = f"https://web.archive.org/web/{timestamp}/{url}"
    try:
        resp = await client.get(wayback_url, timeout=15)
        if resp.status_code != 200:
            return None
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Get name from h1
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        title_tag = soup.find("title")
        if title_tag:
            name = title_tag.get_text(strip=True).split("|")[0].strip()
    if not name:
        return None

    # Get description from content
    description = ""
    main_content = soup.find("main") or soup.find(class_=re.compile(r"content"))
    if main_content:
        paragraphs = main_content.find_all("p")
        for p in paragraphs:
            text = p.get_text(strip=True)
            if len(text) > 40 and not text.startswith("©"):
                description = text
                break

    # Check for test type and metadata in the page
    test_type = ""
    remote_testing = False
    adaptive_irt = False

    # Look for metadata section/table on the detail page
    page_text = soup.get_text().lower()

    # Check for filled circles indicating remote/adaptive
    all_spans = soup.find_all("span", class_=re.compile(r"catalogue__circle"))
    for span in all_spans:
        classes = " ".join(span.get("class", []))
        parent_text = span.parent.get_text(strip=True) if span.parent else ""
        if "fill" in classes:
            if "remote" in parent_text.lower():
                remote_testing = True
            elif "adaptive" in parent_text.lower() or "irt" in parent_text.lower():
                adaptive_irt = True

    # Look for test type in spans or dedicated elements
    type_el = soup.find(string=re.compile(r"Test Type|Assessment Type"))
    if type_el:
        parent = type_el.parent
        if parent:
            sibling = parent.find_next_sibling()
            if sibling:
                test_type = sibling.get_text(strip=True)

    # Fix URL to original (non-wayback)
    clean_url = url if url.startswith("http") else f"https://www.shl.com{url}"

    return {
        "name": name,
        "url": clean_url,
        "description": description,
        "test_type": test_type,
        "remote_testing": remote_testing,
        "adaptive_irt": adaptive_irt,
    }


def is_job_solution(url: str, name: str) -> bool:
    """Check if this is a pre-packaged Job Solution (to exclude)."""
    slug = url.split("/view/")[-1].rstrip("/").lower()
    name_lower = name.lower()

    for pattern in JOB_SOLUTION_PATTERNS:
        if pattern in slug or pattern in name_lower:
            return True
    return False


async def scrape_catalog():
    """Build the full catalog by fetching all detail pages."""
    print("=== Getting all catalog URLs from CDX ===")
    all_urls = await get_all_detail_urls()
    print(f"Found {len(all_urls)} detail page URLs")

    # Load existing data from table scraping (has test_type info)
    existing = {}
    if os.path.exists(OUTPUT_PATH):
        with open(OUTPUT_PATH) as f:
            for item in json.load(f):
                existing[item["url"]] = item

    print(f"Already have {len(existing)} items from table scraping")

    # Fetch detail pages in batches
    all_assessments = list(existing.values())
    seen_urls = set(a["url"] for a in all_assessments)
    seen_names = set(a["name"] for a in all_assessments)

    batch_size = 5  # Concurrent requests
    to_fetch = [(url, ts) for url, ts in all_urls if url not in seen_urls]
    print(f"Need to fetch {len(to_fetch)} new detail pages")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=30) as client:
        for i in range(0, len(to_fetch), batch_size):
            batch = to_fetch[i:i + batch_size]
            tasks = [fetch_detail_page(client, url, ts) for url, ts in batch]
            results = await asyncio.gather(*tasks)

            for result in results:
                if result and result["name"] not in seen_names:
                    # Skip job solutions
                    if not is_job_solution(result["url"], result["name"]):
                        seen_names.add(result["name"])
                        seen_urls.add(result["url"])
                        all_assessments.append(result)

            fetched = min(i + batch_size, len(to_fetch))
            if fetched % 50 == 0 or fetched == len(to_fetch):
                print(f"  Progress: {fetched}/{len(to_fetch)} fetched, {len(all_assessments)} total assessments")

            await asyncio.sleep(0.3)

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_assessments, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*50}")
    print(f"Total assessments: {len(all_assessments)}")
    print(f"Saved to: {OUTPUT_PATH}")

    return all_assessments


if __name__ == "__main__":
    asyncio.run(scrape_catalog())
