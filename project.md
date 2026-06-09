# Project Notes - ShopBot OpenAI Migration

## Current State

The project was rolled back to the stable pre-migration codebase, then migrated narrowly from Groq to OpenAI. Database files were kept stable after rollback.

Current active models:

- STT: `gpt-4o-mini-transcribe`
- LLM: `gpt-4.1`
- TTS: `gpt-4o-mini-tts`
- Voice: `alloy`
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2`

## Provider Migration

OpenAI is now used for:

- `agent/stt.py`: audio transcription
- `agent/llm.py`: Chat Completions JSON response
- `agent/tts.py`: MP3 speech generation
- `scripts/generate_synthetic_data.py`: optional product generation

`requirements.txt` uses `openai>=1.40.0`. The Groq dependency has been removed.

## Database

Important: do not make schema changes unless intentionally doing a migration.

Stable DB files:

- `db/schema.sql`
- `db/database.py`
- `db/seed.py`

Runtime DB:

- PostgreSQL via Docker Compose
- Container image: `pgvector/pgvector:pg16`
- App connection: `postgresql://shopbot:shopbot_password@localhost:5433/shopping_db`
- Product embeddings use pgvector `vector(384)`

The app seeds from `products.json` only when the `products` table is empty.

## RAG And Conversation Behavior

RAG uses `agent/rag.py`:

- Embeds user query with sentence-transformers.
- Searches PostgreSQL using pgvector cosine similarity.
- Applies price constraints when present.
- Falls back to DB price search for budget-only cases.
- Includes a concept fallback for broad human intent such as `healthy`, mapping it to real catalog terms like `apple`, `fruit`, `fresh`, `organic`, `vegetables`, and `groceries`.

This was added because a user can ask "show me something healthy" without naming a product. The assistant should still show real matching inventory instead of claiming nothing exists.

## Grounding Guardrail

`agent/orchestrator.py` has an inventory grounding gate after the LLM response and before TTS.

Purpose:

- Keep spoken response and UI synced.
- Allow broad human intent like `healthy`.
- Block explicit unavailable items like `ice cream` when no retrieved product text contains those item terms.
- Clear UI actions for unavailable explicit products.

Verified examples:

- `Show me something healthy.` returns real grocery/fruit-like products through RAG fallback.
- `Bro, do you have apple? Like, apple is healthy, right?` retrieves Apple.
- `Okay, I will take ice cream.` becomes `out_of_stock` with no UI actions if ice cream is not in retrieved inventory.

## Audio Notes

The frontend records microphone audio as WebM. The WebSocket path historically passed `audio.wav`, which caused newer OpenAI transcription models to reject the audio format.

`agent/stt.py` now detects audio container bytes and sends the correct filename/MIME:

- WebM
- WAV
- OGG
- MP3
- M4A/MP4

OpenAI TTS returns MP3 bytes. Frontend playback expects `audio/mp3`.

## Known Commands

Start database:

```powershell
docker-compose up -d
```

Start app:

```powershell
python run.py
```

Reseed catalog after changing `products.json`:

```powershell
python -m db.seed
```

Useful quick checks:

```powershell
python -c "import config; print(config.STT_MODEL, config.LLM_MODEL, config.TTS_MODEL)"
python -c "from agent.rag import retrieve; print([(p['id'], p['name']) for p in retrieve('show me something healthy')])"
```

## Things To Avoid

- Do not switch PostgreSQL schemas casually.
- Do not edit DB schema/seeding to fix provider issues.
- Do not let the LLM mention products without real DB IDs in `SHOW_PRODUCTS`.
- Do not label browser WebM audio as WAV.
- Do not hard-code a product count; `products.json` is the source.
