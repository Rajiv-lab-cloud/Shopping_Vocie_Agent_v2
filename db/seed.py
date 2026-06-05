"""
Seed the database with products from the local products.json file.
Run: python -m db.seed
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.rag import _embed, _product_to_text  # noqa: E402
from db.database import get_db, init_db  # noqa: E402


def format_category_name(slug: str) -> str:
    mapping = {
        "beauty": "Beauty",
        "fragrances": "Fragrances",
        "furniture": "Furniture",
        "groceries": "Groceries",
        "home-decoration": "Home Decor",
        "kitchen-accessories": "Kitchen Accessories",
        "laptops": "Laptops",
        "mens-shirts": "Men's Shirts",
        "mens-shoes": "Men's Shoes",
        "mens-watches": "Men's Watches",
        "mobile-accessories": "Mobile Accessories",
        "motorcycle": "Motorcycle Accessories",
        "skin-care": "Skin Care",
        "smartphones": "Smartphones",
        "sports-accessories": "Sports Accessories",
        "sunglasses": "Sunglasses",
        "tablets": "Tablets",
        "tops": "Women's Tops",
        "vehicle": "Automotive",
        "womens-bags": "Women's Bags",
        "womens-dresses": "Women's Dresses",
        "womens-jewellery": "Women's Jewellery",
        "womens-shoes": "Women's Shoes",
        "womens-watches": "Women's Watches",
    }
    return mapping.get(slug, slug.replace("-", " ").title())


def seed():
    """Read products.json and seed the Postgres database."""
    json_path = Path(__file__).parent.parent / "products.json"
    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        sys.exit(1)

    print(f"Reading product data from {json_path}...")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading JSON file: {exc}")
        sys.exit(1)

    products = data.get("products", [])
    if not products:
        print("No products found in the JSON file.")
        sys.exit(1)

    print(f"Retrieved {len(products)} products from local file. Seeding database...")
    init_db()

    with get_db() as conn:
        # Clear existing data first
        conn.execute("TRUNCATE products, categories, cart RESTART IDENTITY CASCADE")

        # Insert categories dynamically
        categories = set(p["category"] for p in products)
        cat_id_map = {}
        for cat_slug in categories:
            cat_name = format_category_name(cat_slug)
            conn.execute(
                "INSERT INTO categories (name, slug) VALUES (%s, %s) ON CONFLICT (name) DO NOTHING",
                (cat_name, cat_slug),
            )
            # Fetch inserted ID
            row = conn.execute(
                "SELECT id FROM categories WHERE name = %s", (cat_name,)
            ).fetchone()
            cat_id_map[cat_slug] = row["id"] if isinstance(row, dict) else row[0]

        # Process embeddings in a batch to save time
        print("Computing embeddings for all products...")
        product_texts = []
        for p in products:
            img_list = p.get("images", [])
            img_url = json.dumps(img_list) if img_list else ""

            item_tags = p.get("tags", [])
            if p["category"] not in item_tags:
                item_tags.append(p["category"])
            tags_str = json.dumps(item_tags)

            usd_price = p.get("price", 0.0)
            inr_price = round(usd_price * 80, 2)

            # Reconstruct the product dict locally to match what _product_to_text expects
            temp_p = {
                "name": p["title"],
                "brand": p.get("brand", "AI-KART"),
                "category_name": format_category_name(p["category"]),
                "description": p["description"],
                "price": inr_price,
                "color": "",
                "tags": tags_str,
                "rating": p.get("rating", 4.0),
            }
            product_texts.append(_product_to_text(temp_p))

        # Get all embeddings in one shot
        embeddings = _embed(product_texts)

        # Insert products
        print("Inserting products with embeddings into database...")
        for i, p in enumerate(products):
            cat_id = cat_id_map[p["category"]]

            img_list = p.get("images", [])
            img_url = json.dumps(img_list) if img_list else ""

            item_tags = p.get("tags", [])
            if p["category"] not in item_tags:
                item_tags.append(p["category"])
            tags_str = json.dumps(item_tags)

            usd_price = p.get("price", 0.0)
            inr_price = round(usd_price * 80, 2)
            original_price = round(
                inr_price * (1 + p.get("discountPercentage", 10.0) / 100), 2
            )

            rating = p.get("rating", 4.0)
            review_count = len(p.get("reviews", [])) * 15 + 10
            stock = p.get("stock", 100)
            brand = p.get("brand", "AI-KART")

            conn.execute(
                """
                INSERT INTO products
                  (name, brand, category_id, description, price, original_price,
                   color, size_options, tags, rating, review_count, stock, image_url, is_active, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)
                """,
                (
                    p["title"],
                    brand,
                    cat_id,
                    p["description"],
                    inr_price,
                    original_price,
                    "",
                    "[]",
                    tags_str,
                    rating,
                    review_count,
                    stock,
                    img_url,
                    embeddings[i],
                ),
            )

    print(
        f"[+] Successfully seeded {len(products)} products across {len(categories)} categories."
    )


if __name__ == "__main__":
    seed()
