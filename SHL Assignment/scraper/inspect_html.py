from bs4 import BeautifulSoup

with open("data/catalog_raw.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Check content cards
cards = soup.find_all(class_="content-card")
print(f"Content cards: {len(cards)}")
for card in cards[:10]:
    title_el = card.find(class_="content-card__title")
    link = card.find("a")
    title_text = title_el.get_text(strip=True) if title_el else "N/A"
    link_href = link.get("href") if link else "N/A"
    print(f"  Title: {title_text}")
    print(f"  Link: {link_href}")
    print()

# Breadcrumbs
breadcrumbs = soup.find(class_="breadcrumbs__list")
if breadcrumbs:
    print(f"Breadcrumbs: {breadcrumbs.get_text(strip=True)}")

# Page title
title_tag = soup.find("title")
print(f"Page title: {title_tag.get_text(strip=True) if title_tag else 'N/A'}")

# Canonical URL
canonical = soup.find("link", rel="canonical")
print(f"Canonical: {canonical.get('href') if canonical else 'N/A'}")

# Check the URL that's actually in the response
# Check og:url meta tag
og_url = soup.find("meta", property="og:url")
print(f"og:url: {og_url.get('content') if og_url else 'N/A'}")
