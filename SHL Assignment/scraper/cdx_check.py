import httpx, asyncio, json

async def main():
    headers = {"User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
        cdx_url = "https://web.archive.org/cdx/search/cdx?url=www.shl.com/solutions/products/product-catalog/*&output=json&limit=500&filter=statuscode:200"
        resp = await client.get(cdx_url)
        data = json.loads(resp.text)
        print(f"Total URLs: {len(data)-1}")
        originals = set()
        for row in data[1:]:
            originals.add(row[2])
        print(f"Unique URLs: {len(originals)}")
        for u in sorted(originals):
            print(f"  {u}")

asyncio.run(main())
