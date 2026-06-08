"""
Text-to-Speech module using OpenAI's TTS API.
Returns MP3 audio bytes that can be base64-encoded and sent to the frontend.
"""

import base64
import logging

from openai import OpenAI, RateLimitError

import config

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_tts(text: str) -> bytes:
    client = _get_client()
    try:
        response = client.audio.speech.create(
            model=config.TTS_MODEL,
            voice=config.TTS_VOICE,
            input=text,
            response_format="mp3",
        )
        return response.read()
    except Exception as exc:
        if isinstance(exc, RateLimitError) or (
            hasattr(exc, "status_code") and exc.status_code == 429
        ):
            logger.warning("OpenAI TTS rate limit reached for %s", config.TTS_MODEL)
        raise exc


def synthesize(text: str) -> bytes:
    """
    Convert text to speech using OpenAI TTS.

    This API path returns MP3. If TTS fails, the orchestrator degrades to
    text-only instead of returning audio bytes with the wrong MIME type.
    """
    if len(text) > 4000:
        text = text[:3997] + "..."

    try:
        audio_bytes = _call_tts(text)
    except Exception as exc:
        logger.error("TTS | OpenAI TTS failed: %s", exc)
        raise RuntimeError(f"Text-to-speech failed: {exc}") from exc

    logger.info("TTS | synthesized %d bytes for %d chars", len(audio_bytes), len(text))
    return audio_bytes


def synthesize_b64(text: str) -> str:
    """
    Convert text to speech and return base64-encoded MP3 string.
    Convenient for embedding directly in JSON API responses.
    """
    audio_bytes = synthesize(text)
    return base64.b64encode(audio_bytes).decode("utf-8")
