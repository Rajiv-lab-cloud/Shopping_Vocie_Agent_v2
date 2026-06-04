import json
import sys
import urllib.request
from pathlib import Path


def main():
    url = "https://fakestoreapi.com/products"
    try:
        print(f"Fetching data from {url}...")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        response = urllib.request.urlopen(req)
        data = json.loads(response.read())
    except Exception as e:
        print(f"Error fetching from {url}: {e}")
        sys.exit(1)

    json_path = Path(__file__).parent.parent / "products.json"
    if json_path.exists():
        existing_data = json.loads(json_path.read_text(encoding="utf-8"))
        products = existing_data.get("products", [])
    else:
        existing_data = {}
        products = []

    # Get max id to avoid collisions
    max_id = max((p.get("id", 0) for p in products), default=0)

    added = 0
    for item in data:
        max_id += 1
        new_prod = {
            "id": max_id,
            "title": item.get("title", ""),
            "description": item.get("description", ""),
            "category": item.get("category", "Uncategorized"),
            "price": item.get("price", 0.0),
            "discountPercentage": 0.0,
            "rating": item.get("rating", {}).get("rate", 4.0)
            if isinstance(item.get("rating"), dict)
            else 4.0,
            "stock": 100,
            "tags": [item.get("category", "Uncategorized")]
            if item.get("category")
            else [],
            "brand": "FakeStore",
            "images": [item.get("image")] if item.get("image") else [],
            "reviews": [],
        }
        # Avoid exact duplicates by title
        if any(p.get("title") == new_prod["title"] for p in products):
            continue

        products.append(new_prod)
        added += 1

    existing_data["products"] = products
    json_path.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")
    print(f"Added {added} products from FakeStore API to products.json.")


if __name__ == "__main__":
    main()
