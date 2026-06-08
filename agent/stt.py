"""
Speech-to-Text module using OpenAI's Whisper API.
Accepts raw audio bytes in any format and returns a transcript string.
"""

import io
import logging
from pathlib import Path

from openai import OpenAI, RateLimitError

import config

logger = logging.getLogger(__name__)

# Lazy-loaded client (created once per process)
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
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
def _call_stt(audio_file: tuple, language: str) -> str:
    client = _get_client()
    try:
        request = {
            "model": config.STT_MODEL,
            "file": audio_file,
            "response_format": "text",
            "temperature": 0.0,
        }
        if language:
            request["language"] = language

        response = client.audio.transcriptions.create(**request)
        if isinstance(response, str):
            return response.strip()
        return str(getattr(response, "text", response)).strip()
    except Exception as exc:
        if isinstance(exc, RateLimitError) or (
            hasattr(exc, "status_code") and exc.status_code == 429
        ):
            logger.warning("OpenAI STT rate limit reached for %s", config.STT_MODEL)
        raise exc


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe audio bytes to text using OpenAI Whisper.

    Args:
        audio_bytes: Raw audio data (WAV, MP3, WebM, OGG, M4A, FLAC).
        filename:    Hint for the file extension so OpenAI picks the right decoder.

    Returns:
        Transcript string (stripped of leading/trailing whitespace).

    Raises:
        RuntimeError: On API failure.
    """
    # Wrap bytes in a file-like object; the SDK accepts a tuple with filename and MIME type.
    audio_file = (filename, io.BytesIO(audio_bytes), _mime_type(filename))

    try:
        transcript = _call_stt(audio_file, config.STT_LANGUAGE)
        logger.info("STT | transcript length=%d", len(transcript))
        return transcript

    except Exception as exc:
        logger.error("STT | OpenAI Whisper failed: %s", exc)
        raise RuntimeError("I didn't catch that. Please try again.") from exc


def _mime_type(filename: str) -> str:
    """Return MIME type based on file extension."""
    ext = Path(filename).suffix.lower()
    mapping = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".mp4": "audio/mp4",
    }
    return mapping.get(ext, "audio/wav")
