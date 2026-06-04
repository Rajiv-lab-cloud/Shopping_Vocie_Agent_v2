"""
RAG (Retrieval-Augmented Generation) engine.
Uses PostgreSQL + pgvector for vector similarity search and sentence-transformers for embeddings.
"""

import json
import logging
import re
import threading
from typing import Optional

import numpy as np

import config
from db.database import get_db

logger = logging.getLogger(__name__)

# Lazy globals (loaded once)
_lock = threading.Lock()
_embedder = None


# Embedder


def _get_embedder():
    """Lazy-load the sentence-transformer model (thread-safe)."""
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                from sentence_transformers import SentenceTransformer

                logger.info("RAG | Loading embedding model: %s", config.EMBEDDING_MODEL)
                _embedder = SentenceTransformer(config.EMBEDDING_MODEL)
                logger.info("RAG | Embedding model loaded.")
    return _embedder


def _embed(texts: list[str]) -> np.ndarray:
    """Embed a list of texts into unit-normalized vectors (for cosine sim)."""
    embedder = _get_embedder()
    vecs = embedder.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vecs.astype(np.float32)


# Price constraint extraction


def extract_price_constraints(query: str) -> dict:
    """
    Parse price constraints from a user's natural language query.

    Returns a dict with optional keys:
        max_price (float): Upper price limit  ("under 300", "below 500", "less than 1000")
        min_price (float): Lower price limit  ("above 200", "over 500", "more than 100")
    """
    constraints = {}
    q = query.lower().strip()

    # Pattern: "between X and Y" / "from X to Y"
    between_pat = re.compile(
        r"(?:between|from)\s+(?:₹|rs\.?|rupees?)?\s*(\d+(?:[.,]\d+)?)"
        r"\s*(?:and|to|-)\s*"
        r"(?:₹|rs\.?|rupees?)?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )
    m = between_pat.search(q)
    if m:
        lo = float(m.group(1).replace(",", ""))
        hi = float(m.group(2).replace(",", ""))
        constraints["min_price"] = min(lo, hi)
        constraints["max_price"] = max(lo, hi)
        logger.info("RAG | Price constraint (between): %s", constraints)
        return constraints

    # Pattern: "under / below / less than / within / upto / at most / max / cheaper than X"
    max_pat = re.compile(
        r"(?:under|below|less\s+than|within|upto|up\s+to|at\s+most|max|maximum|cheaper\s+than|not\s+(?:more|above)\s+(?:than)?)"
        r"\s*(?:₹|rs\.?|rupees?)?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )
    m = max_pat.search(q)
    if m:
        constraints["max_price"] = float(m.group(1).replace(",", ""))

    # Pattern: "above / over / more than / at least / min / starting from / costlier than X"
    min_pat = re.compile(
        r"(?:above|over|more\s+than|at\s+least|min|minimum|starting\s+from|costlier\s+than|not\s+(?:less|below|under)\s+(?:than)?)"
        r"\s*(?:₹|rs\.?|rupees?)?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )
    m = min_pat.search(q)
    if m:
        constraints["min_price"] = float(m.group(1).replace(",", ""))

    # Pattern: "I (only) have X rupees" / "my budget is X" / "budget X"
    budget_pat = re.compile(
        r"(?:i\s+(?:only\s+)?have|(?:my\s+)?budget\s+(?:is)?)\s*(?:₹|rs\.?|rupees?)?\s*(\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )
    m = budget_pat.search(q)
    if m and "max_price" not in constraints:
        constraints["max_price"] = float(m.group(1).replace(",", ""))

    # Pattern: standalone "X rupees" with implicit budget context (only if no other constraint found)
    if not constraints:
        rupee_pat = re.compile(
            r"(?:₹|rs\.?)\s*(\d+(?:[.,]\d+)?)|(\d+(?:[.,]\d+)?)\s*(?:₹|rs\.?|rupees?)",
            re.IGNORECASE,
        )
        m = rupee_pat.search(q)
        if m:
            val = float((m.group(1) or m.group(2)).replace(",", ""))
            # If the query tone suggests a budget/limit, treat as max_price
            if any(
                word in q
                for word in ["only", "just", "budget", "afford", "cheap", "save"]
            ):
                constraints["max_price"] = val

    if constraints:
        logger.info(
            "RAG | Price constraints extracted: %s from query: %r",
            constraints,
            query[:80],
        )
    return constraints


# Retrieval


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    top_n: Optional[int] = None,
    price_constraints: Optional[dict] = None,
) -> list[dict]:
    """
    Retrieve the most relevant products for a user query directly from Postgres.

    Args:
        query:              User's natural language query.
        top_k:              Ignored, kept for signature compatibility.
        top_n:              Final number of products to return after re-ranking.
        price_constraints:  Optional dict with 'max_price' and/or 'min_price' keys.
                            If not provided, constraints are auto-extracted from the query.

    Returns:
        List of product dicts (top_n most relevant), filtered by price if applicable.
    """
    n = top_n or config.RAG_TOP_N

    # Auto-extract price constraints from query if not explicitly provided
    if price_constraints is None:
        price_constraints = extract_price_constraints(query)

    query_vec = _embed([query])[0]

    conditions = ["p.is_active = 1"]
    params = []

    # Cosine distance operator <=> (distance = 1 - cosine similarity)
    # We want similarity = 1 - distance

    # We add the embedding to the params
    params.append(query_vec)
    params.append(query_vec)  # For the ORDER BY

    max_price = price_constraints.get("max_price") if price_constraints else None
    min_price = price_constraints.get("min_price") if price_constraints else None

    if max_price is not None:
        conditions.append("p.price <= %s")
        params.append(max_price)
    if min_price is not None:
        conditions.append("p.price >= %s")
        params.append(min_price)

    where_clause = " AND ".join(conditions)
    params.append(n * 2)  # Fetch extra to filter out low similarities

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*, c.name AS category_name, c.slug AS category_slug,
                   1 - (p.embedding <=> %s) AS _semantic_score
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE {where_clause}
            ORDER BY p.embedding <=> %s
            LIMIT %s
            """,
            params,
        ).fetchall()

    candidate_products = [dict(row) for row in rows]

    # Filter out weak semantic matches (cosine similarity < 0.3)
    filtered_products = [p for p in candidate_products if p["_semantic_score"] >= 0.3]

    # If price filtering + weak semantic match filter removed everything, try a DB-level fallback
    if not filtered_products and price_constraints:
        logger.info("RAG | Filter removed all candidates — trying DB fallback")
        filtered_products = _price_fallback_from_db(price_constraints, n)
        for p in filtered_products:
            p["_semantic_score"] = 0.0

    # Sort by semantic score descending (in case fallback was used, or just to be safe)
    filtered_products.sort(key=lambda p: p["_semantic_score"], reverse=True)

    result = filtered_products[:n]
    logger.info(
        "RAG | query=%r | returned=%d | top_score=%.3f | price_filter=%s",
        query[:60],
        len(result),
        result[0]["_semantic_score"] if result else 0,
        price_constraints or "none",
    )
    return result


def _price_fallback_from_db(constraints: dict, limit: int) -> list[dict]:
    """
    Fallback: query the database directly with price constraints
    when semantic search + price filter yields no results.
    """
    from db.database import get_db

    max_price = constraints.get("max_price")
    min_price = constraints.get("min_price")

    conditions = ["p.is_active = 1"]
    params = []

    if max_price is not None:
        conditions.append("p.price <= %s")
        params.append(max_price)
    if min_price is not None:
        conditions.append("p.price >= %s")
        params.append(min_price)

    where_clause = " AND ".join(conditions)
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*, c.name AS category_name, c.slug AS category_slug
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE {where_clause}
            ORDER BY p.rating DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    results = [dict(row) for row in rows]
    logger.info("RAG | DB price fallback returned %d products", len(results))
    return results


def preload() -> None:
    """Preload the embedding model."""
    logger.info("RAG | Preloading models...")
    _get_embedder()
    logger.info("RAG | Preload complete.")


# Helpers


def _product_to_text(product: dict) -> str:
    """
    Convert a product dict into a rich text string for embedding.
    """
    tags = ""
    try:
        tags = ", ".join(json.loads(product.get("tags") or "[]"))
    except (json.JSONDecodeError, TypeError):
        tags = str(product.get("tags", ""))

    return (
        f"{product['name']} by {product['brand']}. "
        f"Category: {product.get('category_name', '')}. "
        f"Color: {product.get('color', '')}. "
        f"Price: {int(product['price'])} rupees. "
        f"Description: {product['description']}. "
        f"Tags: {tags}. "
        f"Rating: {product['rating']} stars."
    )
