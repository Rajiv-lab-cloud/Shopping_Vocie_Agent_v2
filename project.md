# Shopping Voice Agent — Project Notes (OpenAI Provider Migration)

## What changed

- Migrated LLM/STT/TTS provider from Groq to OpenAI.
- Removed direct Groq runtime dependency and replaced with `openai` package in `requirements.txt`.
- Kept temporary compatibility support for legacy `GROQ_API_KEY` in `config.py` and synthetic data script only for migration safety.
- Updated runtime checks/startup messaging in `run.py` to validate `OPENAI_API_KEY`.
- Updated API schema/model wording and docs to reflect MP3 TTS payload in frontend (frontend expects `audio/mp3` in `data:` URI).

## Files updated

- `config.py`: replaced provider keys and model defaults.
  - `OPENAI_API_KEY` now primary key (`GROQ_API_KEY` fallback kept).
  - `STT_MODEL=whisper-1`
  - `LLM_MODEL=gpt-4o-mini`
  - `TTS_MODEL=tts-1`
  - `TTS_VOICE=alloy`
- `agent/llm.py`: switched from `groq.Groq` to `openai.OpenAI` client; updated error handling/logging.
- `agent/stt.py`: switched to `openai.OpenAI.audio.transcriptions.create(...)`.
- `agent/tts.py`: switched to `openai.OpenAI.audio.speech.create(...)` and set response format to `mp3`.
- `scripts/generate_synthetic_data.py`: switched to OpenAI API usage and default to `gpt-4o-mini`.
- `api/main.py`, `api/models.py`, `agent/orchestrator.py`: description and comments now reference OpenAI.
- `run.py`: changed bootstrap messaging and `.env` validation to `OPENAI_API_KEY`.
- `requirements.txt`: replaced Groq SDK with `openai>=1.40.0`.
- `README.md`: updated model/provider references from Groq to OpenAI.
- `.env` / `.env.example`: replaced with OpenAI keys and default models.

## Current model defaults

- STT: `whisper-1`
- LLM: `gpt-4o-mini`
- TTS: `tts-1` with voice `alloy`

## How to run

1. Create/refresh environment:
   - `copy .env.example .env` (Windows) or equivalent
   - set `OPENAI_API_KEY` in `.env`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Start services:
   - `docker-compose up -d`
4. Start app:
   - `python run.py`

## Known notes

- The frontend expects `audio/mp3` payloads (base64 in `audio_b64`), so TTS response format is set to `mp3`.
- A legacy fallback key (`GROQ_API_KEY`) is still read only if `OPENAI_API_KEY` is missing.
- `products.json` remains the full product source file for DB seeding; no structural change was made to product schema.
