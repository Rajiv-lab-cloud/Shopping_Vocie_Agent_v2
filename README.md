# ShopBot - Voice AI Shopping Assistant

ShopBot is a voice-enabled AI shopping assistant for an e-commerce storefront. A customer can speak naturally, the backend transcribes the audio, retrieves matching products from PostgreSQL + pgvector, asks an OpenAI LLM for a structured shopping response, updates the UI with actions, and returns spoken audio.

## Current Stack

| Layer | Technology | Current default |
| --- | --- | --- |
| STT | OpenAI audio transcription | `gpt-4o-mini-transcribe` |
| LLM | OpenAI Chat Completions JSON mode | `gpt-4.1` |
| TTS | OpenAI speech generation | `gpt-4o-mini-tts` |
| Embeddings | sentence-transformers | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector DB | PostgreSQL + pgvector | Docker service on port `5433` |
| API | FastAPI + Uvicorn | `api.main:app` |
| Frontend | React + Vite static build | served by FastAPI |

## Pipeline

```text
Browser audio/text
  -> OpenAI STT
  -> input guardrails
  -> RAG retrieval from PostgreSQL + pgvector
  -> OpenAI LLM JSON response
  -> inventory/output guardrails
  -> OpenAI TTS MP3
  -> frontend UI actions + spoken response
```

## Key Behavior

- Uses `products.json` as the catalog seed source.
- Stores products, categories, cart, profile, and embeddings in PostgreSQL.
- Uses pgvector similarity search for product retrieval.
- Falls back from broad human concepts to concrete catalog terms. For example, `healthy` maps to available grocery/fruit/fresh-product terms, so the assistant can show real items like Apple, Kiwi, Mulberry, or Water if present.
- Blocks unavailable explicit items before TTS. For example, if the user asks for `ice cream` and no retrieved product actually contains that item, the response becomes out-of-stock and UI actions are cleared.
- Keeps voice and UI synced by only speaking about products that are backed by DB product IDs.
- Detects real uploaded audio container type from bytes, so browser WebM audio is sent to OpenAI as WebM instead of being mislabeled as WAV.

## Quick Start

```powershell
cd C:\Users\admin\Desktop\Shopping_Vocie_Agent_v2
copy .env.example .env
```

Set your key in `.env`:

```env
OPENAI_API_KEY=your_openai_api_key_here
```

Start PostgreSQL:

```powershell
docker-compose up -d
```

Run the app:

```powershell
python run.py
```

`run.py` checks dependencies, builds the frontend, validates `OPENAI_API_KEY`, initializes the DB schema, seeds products only if the products table is empty, then starts FastAPI.

## Environment Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | required | OpenAI API key |
| `STT_MODEL` | `gpt-4o-mini-transcribe` | Speech-to-text model |
| `LLM_MODEL` | `gpt-4.1` | Chat model for shopping decisions |
| `TTS_MODEL` | `gpt-4o-mini-tts` | Text-to-speech model |
| `TTS_VOICE` | `alloy` | OpenAI TTS voice |
| `DATABASE_URL` | `postgresql://shopbot:shopbot_password@localhost:5433/shopping_db` | PostgreSQL connection |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Product embedding model |
| `RAG_TOP_K` | `10` | Retrieval compatibility setting |
| `RAG_TOP_N` | `3` | Number of products passed to the LLM |
| `PORT` | `8000` | API server port |

## API

### `POST /v1/shop`

Main non-streaming endpoint. Accepts audio or text and returns transcript, response text, UI actions, MP3 audio, and latency timings.

```json
{
  "transcript": "show me something healthy",
  "response_text": "Here are a few healthy options from our groceries section.",
  "intent": "product_search",
  "confidence": 0.98,
  "ui_actions": [
    {"action": "SHOW_PRODUCTS", "params": {"product_ids": [16, 30, 33]}}
  ],
  "audio_b64": "...",
  "latency_ms": {"stt_ms": 420, "rag_ms": 85, "llm_ms": 1200, "tts_ms": 380}
}
```

### `POST /v1/shop/stream`

Server-sent events version of the shopping pipeline.

### `WebSocket /ws/chat`

Realtime chat/voice endpoint used by the frontend.

### Product and Cart Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/products` | List active products |
| `GET /v1/products/by-ids?ids=1,2` | Fetch specific product cards |
| `GET /v1/categories` | List categories |
| `GET /v1/cart` | Get cart |
| `POST /v1/cart/add` | Add item |
| `POST /v1/cart/update` | Update quantity |
| `DELETE /v1/cart/{cart_id}` | Remove item |
| `DELETE /v1/cart` | Clear cart |
| `POST /v1/cart/checkout` | Generate bill and checkout |

## UI Actions

| Action | Purpose |
| --- | --- |
| `SHOW_PRODUCTS` | Show specific product IDs |
| `FILTER_PRODUCTS` | Apply filters |
| `NAVIGATE_TO` | Navigate frontend route |
| `SORT_PRODUCTS` | Sort listing |
| `ADD_TO_CART` | Add product |
| `REMOVE_FROM_CART` | Remove product |
| `UPDATE_CART_QUANTITY` | Change quantity |
| `SHOW_PRODUCT_DETAIL` | Open product detail |
| `CLEAR_FILTERS` | Reset filters |
| `CLEAR_CART` | Empty cart |
| `CHECKOUT` | Complete checkout |
| `CLEAR_HISTORY` | Reset conversation memory |

## Product Data

The catalog source file is `products.json`. To reseed after editing it:

```powershell
python -m db.seed
```

The seeder recalculates embeddings and inserts products into PostgreSQL. The active database currently uses PostgreSQL with `pgvector`, not local FAISS files.

## Important Notes

- Do not reintroduce Groq SDK/config unless intentionally migrating providers again.
- OpenAI TTS returns MP3 and the frontend expects `audio/mp3` payloads.
- Browser microphone recordings are usually WebM/Opus; `agent/stt.py` detects the container before sending audio to OpenAI.
- Keep DB schema files stable unless intentionally doing a database migration.
- If the assistant speaks about a product, the response must include matching UI actions with real DB product IDs.

## Tests

```powershell
pytest tests/test_guardrails.py -v
pytest tests/test_rag.py -v
pytest tests/ -v
```

Some tests require Docker/PostgreSQL and API key configuration.
