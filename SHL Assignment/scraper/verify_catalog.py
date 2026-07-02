import json

with open("data/catalog.json", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total: {len(data)}")
with_type = sum(1 for d in data if d.get("test_type"))
with_desc = sum(1 for d in data if d.get("description"))
print(f"With test_type: {with_type}")
print(f"With description: {with_desc}")

# Sample
for i in [0, 50, 100, 200, 300, 379]:
    if i < len(data):
        d = data[i]
        name = d["name"]
        tt = d.get("test_type", "")
        url = d["url"][:70]
        desc = (d.get("description") or "")[:60]
        print(f"  [{i}] {name} | type={tt} | {url}")
        if desc:
            print(f"       desc: {desc}...")
