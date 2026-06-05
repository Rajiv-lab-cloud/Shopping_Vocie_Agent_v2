"""
generate_synthetic_data.py
Connects to Groq LLaMA to generate diverse synthetic e-commerce products.
"""
import os
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from groq import Groq

# Load .env
load_dotenv(Path(__file__).parent.parent / ".env")

API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    print("Error: GROQ_API_KEY not set.")
    sys.exit(1)

client = Groq(api_key=API_KEY)

# Categories we want to add
CATEGORIES = ["automotive", "electronics", "home-appliances", "toys", "sports", "books", "gaming"]

prompt = f"""You are a helpful data generator. Generate 50 realistic, diverse e-commerce products across these categories: {', '.join(CATEGORIES)}.
Return a JSON object with a single key "products" containing an array of product objects.
Each product object must follow this exact schema:
{{
  "id": 0,
  "title": "<string, product name>",
  "description": "<string, engaging description>",
  "category": "<string, one of the requested categories>",
  "price": <float, USD price, e.g. 19.99>,
  "discountPercentage": <float, e.g. 10.5>,
  "rating": <float, 1.0 to 5.0>,
  "stock": <integer, between 1 and 150>,
  "tags": ["<string>", "<string>"],
  "brand": "<string, realistic brand name>",
  "reviews": [
    {{ "rating": 5, "comment": "<string>" }}
  ],
  "images": ["<string, placeholder url like https://placehold.co/400>"]
}}
Generate realistic product titles, descriptions, and brands. Make sure the output is pure JSON.
"""

def generate_data():
    print("Requesting synthetic data from Groq LLaMA 3.3 70B...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=8000
    )
    
    content = response.choices[0].message.content
    try:
        data = json.loads(content)
        new_products = data.get("products", [])
        print(f"Successfully generated {len(new_products)} products.")
        
        # Read existing
        json_path = Path(__file__).parent.parent / "products.json"
        with open(json_path, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            
        # Determine max id to avoid conflicts
        max_id = max((p["id"] for p in existing_data.get("products", [])), default=0)
        
        # Assign new sequential IDs and append
        for i, p in enumerate(new_products):
            p["id"] = max_id + 1 + i
            # Also adjust the dummy placehold image text to match the product title
            title_url = p["title"].replace(" ", "+")
            p["images"] = [f"https://placehold.co/400?text={title_url}"]
            
        existing_data["products"].extend(new_products)
        
        # Write back
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, indent=2)
            
        print("Updated products.json successfully. Run 'python -m db.seed' to re-seed the database.")
        
    except Exception as e:
        print("Error parsing or saving data:", e)
        print("Raw content:", content)

if __name__ == "__main__":
    generate_data()
