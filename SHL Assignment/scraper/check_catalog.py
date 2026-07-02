import json
with open("data/catalog.json") as f:
    data = json.load(f)
print(f"Current catalog: {len(data)} items")
if data:
    print(f"First: {data[0]['name']}")
    print(f"Last: {data[-1]['name']}")
    # Count by test type
    types = {}
    for item in data:
        tt = item.get("test_type", "")
        types[tt] = types.get(tt, 0) + 1
    print(f"Types: {types}")
