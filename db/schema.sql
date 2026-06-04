CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS categories (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    slug    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    brand           TEXT NOT NULL,
    category_id     INTEGER NOT NULL REFERENCES categories(id),
    description     TEXT NOT NULL,
    price           REAL NOT NULL,          -- INR
    original_price  REAL,                   -- INR (for discount display)
    color           TEXT,
    size_options    TEXT,                   -- JSON array e.g. '["S","M","L"]'
    tags            TEXT,                   -- JSON array e.g. '["casual","summer"]'
    rating          REAL DEFAULT 0.0,
    review_count    INTEGER DEFAULT 0,
    stock           INTEGER DEFAULT 100,
    image_url       TEXT,
    is_active       INTEGER DEFAULT 1,
    embedding       vector(384)
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_price ON products(price);
CREATE INDEX IF NOT EXISTS idx_products_color ON products(color);
CREATE INDEX IF NOT EXISTS idx_products_rating ON products(rating DESC);
CREATE INDEX IF NOT EXISTS idx_products_embedding ON products USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS cart (
    id          SERIAL PRIMARY KEY,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 1,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    id              SERIAL PRIMARY KEY,
    address         TEXT,
    payment_method  TEXT,
    preferences     TEXT
);
