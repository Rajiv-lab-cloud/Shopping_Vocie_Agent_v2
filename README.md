# 🛍️ ShopBot — Voice AI Shopping Assistant

A production-ready voice-enabled AI shopping assistant for e-commerce websites.  
Customers speak naturally → the system understands intent → retrieves products using vector search → controls the website in real-time → responds with voice.

---

## Architecture

Our robust architecture leverages a **modular, multi-model approach** to ensure a highly resilient, fail-safe scenario. Instead of relying on a single monolithic AI, we split the pipeline across specialized models (STT, LLM, TTS, Embeddings) and use a robust PostgreSQL backend for hybrid search fallbacks.

```
Customer Audio (WAV/WebM/MP3)
        │
        ▼
┌─────────────────────┐
│  1. Whisper STT     │  groq: whisper-large-v3-turbo
└──────────┬──────────┘
           │ transcript
           ▼
┌─────────────────────┐
│  2. Input Guardrail │  Injection detection, PII redaction, length check
└──────────┬──────────┘
           │ safe_text
           ▼
┌─────────────────────┐
│  3. RAG Retrieval   │  PostgreSQL (pgvector) + sentence-transformers
│     (Vector DB)     │  Cosine similarity + structured SQL fallbacks
└──────────┬──────────┘
           │ product_context
           ▼
┌─────────────────────┐
│  4. LLM Agent       │  groq: llama-3.3-70b-versatile (JSON mode)
│  System Prompt +    │  → {response_text, intent, ui_actions}
│  Few-shot examples  │
└──────────┬──────────┘
           │ structured_output
           ▼
┌─────────────────────┐
│  5. Output Guardrail│  Validates action types, product IDs, brand safety
└──────────┬──────────┘
           │ validated_output
           ▼
┌─────────────────────┐
│  6. Orpheus TTS     │  groq: canopylabs/orpheus-v1-english
└──────────┬──────────┘
           │ audio_bytes
           ▼
┌─────────────────────┐
│  7. API Response    │  {ui_actions, audio_b64, transcript, response_text}
└─────────────────────┘
```

---

## Tech Stack

| Layer       | Technology                              | Description                               |
|-------------|------------------------------------------|-------------------------------------------|
| **STT**     | `whisper-large-v3-turbo` via Groq        | Ultra-fast speech-to-text                 |
| **LLM**     | `llama-3.3-70b-versatile` via Groq       | Reasoning, entity extraction, and JSON    |
| **TTS**     | `canopylabs/orpheus-v1-english` via Groq | Low-latency voice synthesis               |
| **Embeddings** | `all-MiniLM-L6-v2` (384-dim)         | Semantic vector generation                |
| **Vector DB** | PostgreSQL + `pgvector`                | Advanced hybrid search (semantic + SQL)   |
| **Platform**| Docker & Docker Compose                  | Containerized database and environment    |
| **API**     | FastAPI + Uvicorn                        | High-performance asynchronous API         |
| **Frontend**| Vanilla HTML/CSS/JS                      | Lightweight, reactive web interface       |

---

## Key Features & Highlights

- **Multi-Model Fail-Safe Design**: By separating concerns into highly specialized models (STT, LLM, Embedding, TTS), the pipeline ensures rapid execution and fail-safe redundancy. If semantic search yields no results, the RAG engine automatically falls back to raw SQL price-constraint filtering.
- **PostgreSQL Vector Database**: Replaced legacy SQLite and FAISS files with an enterprise-grade `pgvector` integration. This enables executing advanced cosine similarity (`<=>`) semantic searches intertwined with standard SQL WHERE clauses (like price caps) in a single, lightning-fast database transaction.
- **Dockerized Infrastructure**: A seamless `docker-compose.yml` spins up a robust PostgreSQL 16 instance pre-configured with the `pgvector` extension, guaranteeing a reproducible environment anywhere.
- **Comprehensive Guardrails**: Fully integrated input and output validations. The system actively hunts for prompt injections, redacts PII (emails/phone numbers), clamps out-of-bounds queries, and scrub hallucinated products before they reach the frontend.
- **Real-Time UI Orchestration**: The AI dynamically generates structured JSON `ui_actions` (like `FILTER_PRODUCTS` or `ADD_TO_CART`) which command the frontend UI state without requiring page reloads.
- **Smart Real-Time Inventory Tracking**: The system accurately tracks product stock, prevents users from ordering out-of-stock items, handles checkout stock deductions on the backend, and automatically syncs the frontend UI in near real-time via background polling.
- **Dynamic Synthetic Categories**: Includes an automated LLM-powered data generation pipeline (`scripts/generate_synthetic_data.py`) to easily scale up the catalog with highly diverse, realistic e-commerce products across multiple categories.

---

## 🚀 Upgrades from Version 1 to Version 2

Version 2 introduces several major architectural upgrades to improve performance, scalability, and ease of deployment:
- **Migration to PostgreSQL & pgvector**: Replaced legacy SQLite and FAISS with an enterprise-grade `pgvector` setup. This allows vector similarity searches and SQL filtering in a single query.
- **Dockerized Backend Infrastructure**: A fully containerized PostgreSQL database configured with pgvector out of the box. No manual DB setup required.
- **Modern React + Vite Frontend**: Completely initialized a new frontend project using React and Vite, replacing older basic static HTML/JS rendering.
- **Automated Build Scripts**: The entry point `run.py` now includes `build_frontend()`, which seamlessly installs and builds the React frontend on startup.
- **Robust Error Handling & Connections**: Enhanced database and Docker availability checks to provide helpful fail-safe warnings if the environment is not running.

---

## Quick Start

### 1. Clone & Install

```bash
cd Shopping_Voice_Agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
copy .env.example .env
```

Edit `.env` and set your Groq API key:

```env
GROQ_API_KEY=gsk_your_groq_api_key_here
DATABASE_URL=postgresql://shopbot:shopbot_password@localhost:5433/shopping_db
```

Get a free Groq API key at: https://console.groq.com

### 3. Boot Up the PostgreSQL Database

Ensure you have Docker installed and running, then spin up the database:

```bash
docker-compose up -d
```

### 4. Start the Application

```bash
python run.py
```

This will automatically:
- Check Python versions and dependencies.
- Initialize the PostgreSQL database schema.
- Seed the catalog and instantly compute/insert all vector embeddings into Postgres.
- Start the FastAPI server via uvicorn.
- Open the frontend in your default browser.

---

## API Reference

### `POST /v1/shop` — Main Endpoint

**Request** (`multipart/form-data`):

| Field      | Type   | Required | Description                    |
|------------|--------|----------|--------------------------------|
| `audio`    | File   | Either/Or| Audio file (WAV, MP3, WebM)    |
| `text`     | String | Either/Or| Plain text input for testing   |
| `skip_tts` | Bool   | No       | Skip TTS synthesis (faster)    |

**Response** (`application/json`):

```json
{
  "transcript":    "Show me red shoes under 5000",
  "response_text": "Here are some great red shoes under ₹5,000!",
  "intent":        "product_search",
  "confidence":    0.97,
  "ui_actions": [
    {"action": "FILTER_PRODUCTS", "params": {"color": "red", "max_price": 5000}},
    {"action": "SHOW_PRODUCTS",   "params": {"product_ids": [1, 7]}}
  ],
  "audio_b64":  "UklGRiQA...",
  "latency_ms": {"stt_ms": 420, "rag_ms": 85, "llm_ms": 1200, "tts_ms": 380, "total_ms": 2090}
}
```

### UI Action Types

| Action              | Params                                                      |
|---------------------|-------------------------------------------------------------|
| `SHOW_PRODUCTS`     | `product_ids: [int]`                                        |
| `FILTER_PRODUCTS`   | `category, color, max_price, min_price, min_rating, brand`  |
| `SORT_PRODUCTS`     | `sort_by: "price_asc" \| "price_desc" \| "rating"`         |
| `NAVIGATE_TO`       | `page: "cart" \| "checkout" \| "category/shoes" \| ...`    |
| `ADD_TO_CART`       | `product_id: int`                                           |
| `SHOW_PRODUCT_DETAIL`| `product_id: int`                                          |
| `CLEAR_FILTERS`     | `{}`                                                        |

### `GET /v1/products` — Product Catalog

Returns active products. Use this to populate your frontend's product grid.

---

## Testing

```bash
# Unit tests (no API key needed for guardrail + RAG tests)
pytest tests/test_guardrails.py -v

# RAG tests (needs DB running)
pytest tests/test_rag.py -v

# API tests (uses TestClient, needs GROQ_API_KEY)
pytest tests/test_api.py -v

# Full test suite
pytest tests/ -v
```

---

## Adding Products & Expanding Catalog

There are two ways to add products to your store:
1. **Manual Entry**: Add new product entries directly to `products.json`.
2. **AI Synthetic Generation**: Automatically expand your catalog with diverse new categories using the built-in LLM script:
   ```bash
   python scripts/generate_synthetic_data.py
   ```

After using either method, re-run the seeder to recalculate embeddings and insert them into PostgreSQL:
   ```bash
   python -m db.seed
   ```

---

## Environment Variables

| Variable         | Default                              | Description                   |
|------------------|--------------------------------------|-------------------------------|
| `GROQ_API_KEY`   | *(required)*                         | Groq API key                  |
| `DATABASE_URL`   | *(required)*                         | PostgreSQL connection URL     |
| `STT_MODEL`      | `whisper-large-v3-turbo`             | Groq Whisper model            |
| `LLM_MODEL`      | `llama-3.3-70b-versatile`            | Groq LLM model                |
| `TTS_MODEL`      | `canopylabs/orpheus-v1-english`      | Groq TTS model                |
| `EMBEDDING_MODEL`| `sentence-transformers/all-MiniLM-L6-v2` | Embedding model           |
| `PORT`           | `8000`                               | API server port               |

---

## Groq Models Used

All three AI models are served by [Groq](https://console.groq.com) — the fastest LLM inference platform:

| Model                           | Use          | Speed      |
|---------------------------------|--------------|------------|
| `whisper-large-v3-turbo`        | STT          | ~0.2-0.5s  |
| `llama-3.3-70b-versatile`       | LLM Reasoning| ~0.5-2s    |
| `canopylabs/orpheus-v1-english` | TTS          | ~0.3-0.8s  |

Total pipeline latency: typically **2–4 seconds** end-to-end.
