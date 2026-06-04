"""
PostgreSQL database connection helpers.
Uses psycopg 3 thread-local connections.
"""

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

import config

# Thread-local storage for connections
_local = threading.local()


def _get_connection() -> psycopg.Connection:
    """Return a thread-local Postgres connection, creating one if needed."""
    if not hasattr(_local, "conn") or _local.conn is None or _local.conn.closed:
        conn = psycopg.connect(config.DATABASE_URL, row_factory=dict_row)
        # Ensure extension exists before registering it
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.commit()
        # Register pgvector type
        register_vector(conn)
        _local.conn = conn
    return _local.conn


@contextmanager
def get_db() -> Generator[psycopg.Connection, None, None]:
    """Context manager that yields a DB connection and commits/rolls back."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db() -> None:
    """Create tables from schema.sql if they don't exist."""
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")
    with get_db() as conn:
        conn.execute(schema_sql)


def get_all_products(limit: int = 10000, offset: int = 0) -> list[dict]:
    """Return an even mix of active products across categories."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.*, c.name AS category_name, c.slug AS category_slug
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER(PARTITION BY category_id ORDER BY RANDOM()) as rn
                FROM products
                WHERE is_active = 1
            ) p
            JOIN categories c ON p.category_id = c.id
            WHERE p.rn <= 1000
            ORDER BY RANDOM()
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        ).fetchall()
    return rows


def get_products_by_ids(ids: list[int]) -> list[dict]:
    """Return products matching given IDs."""
    if not ids:
        return []
    placeholders = ",".join("%s" for _ in ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""
            SELECT p.*, c.name AS category_name, c.slug AS category_slug
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE p.id IN ({placeholders}) AND p.is_active = 1
            """,
            ids,
        ).fetchall()
    return rows


def get_products_by_category(category_name: str, limit: int = 50) -> list[dict]:
    """Return active products matching the given category name."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT p.*, c.name AS category_name, c.slug AS category_slug
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE (c.name = %s OR p.tags LIKE %s) AND p.is_active = 1
            LIMIT %s
            """,
            (category_name, f'%%"{category_name}"%%', limit),
        ).fetchall()
    return rows


def product_exists(product_id: int) -> bool:
    """Check whether a product ID exists and is active."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM products WHERE id = %s AND is_active = 1", (product_id,)
        ).fetchone()
    return row is not None


# Cart Helpers


def get_cart_items() -> list[dict]:
    """Return all items in the cart with product details."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT c.id as cart_id, c.quantity, CAST(c.added_at AS TEXT) as added_at, p.*, cat.name AS category_name, cat.slug AS category_slug
            FROM cart c
            JOIN products p ON c.product_id = p.id
            JOIN categories cat ON p.category_id = cat.id
            ORDER BY c.added_at DESC
            """
        ).fetchall()
    return rows


def add_to_cart(product_id: int, quantity: int = 1) -> int:
    """Add a product to the cart or increment quantity if it exists."""
    with get_db() as conn:
        # Check if already in cart
        row = conn.execute(
            "SELECT id, quantity FROM cart WHERE product_id = %s", (product_id,)
        ).fetchone()
        if row:
            new_qty = row["quantity"] + quantity
            conn.execute(
                "UPDATE cart SET quantity = %s WHERE id = %s", (new_qty, row["id"])
            )
            return row["id"]
        else:
            row = conn.execute(
                "INSERT INTO cart (product_id, quantity) VALUES (%s, %s) RETURNING id",
                (product_id, quantity),
            ).fetchone()
            return row["id"]


def update_cart_quantity(product_id: int, quantity: int) -> bool:
    """Update quantity of a specific product in the cart. If <= 0, remove it."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM cart WHERE product_id = %s", (product_id,)
        ).fetchone()
        if not row:
            return False

        if quantity <= 0:
            cursor = conn.execute("DELETE FROM cart WHERE id = %s", (row["id"],))
        else:
            cursor = conn.execute(
                "UPDATE cart SET quantity = %s WHERE id = %s", (quantity, row["id"])
            )

        return cursor.rowcount > 0


def remove_from_cart(cart_id: int) -> bool:
    """Remove a specific item from the cart."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM cart WHERE id = %s", (cart_id,))
        return cursor.rowcount > 0


def clear_cart() -> None:
    """Empty the cart."""
    with get_db() as conn:
        conn.execute("DELETE FROM cart")


# User Profile Helpers


def get_user_profile() -> dict:
    """Return the current user profile (address, payment_method, preferences)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT address, payment_method, preferences FROM user_profile WHERE id = 1"
        ).fetchone()
        if row:
            return row
        return {"address": None, "payment_method": None, "preferences": None}


def update_user_profile(address: str, payment_method: str) -> None:
    """Update or insert the user profile."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM user_profile WHERE id = 1").fetchone()
        if row:
            conn.execute(
                "UPDATE user_profile SET address = %s, payment_method = %s WHERE id = 1",
                (address, payment_method),
            )
        else:
            conn.execute(
                "INSERT INTO user_profile (id, address, payment_method) VALUES (1, %s, %s)",
                (address, payment_method),
            )

def update_user_preferences(preferences: str) -> None:
    """Update the user's long-term preferences."""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM user_profile WHERE id = 1").fetchone()
        if row:
            conn.execute(
                "UPDATE user_profile SET preferences = %s WHERE id = 1",
                (preferences,),
            )
        else:
            conn.execute(
                "INSERT INTO user_profile (id, preferences) VALUES (1, %s)",
                (preferences,),
            )
