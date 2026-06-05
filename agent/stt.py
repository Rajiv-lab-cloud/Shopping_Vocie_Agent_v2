"""
Speech-to-Text module using Groq's Whisper API.
Accepts raw audio bytes in any format and returns a transcript string.
"""

import io
import logging
from pathlib import Path

from groq import Groq

import config

logger = logging.getLogger(__name__)

# Lazy-loaded client (created once per process)
_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
        _client = Groq(api_key=config.GROQ_API_KEY)
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
        return str(response).strip()
    except Exception as exc:
        import groq

        if isinstance(exc, groq.RateLimitError) or (
            hasattr(exc, "status_code") and exc.status_code == 429
        ):
            fallbacks = [
                "whisper-large-v3-turbo",
                "whisper-large-v3",
                "distil-whisper-large-v3-en",
            ]
            if config.STT_MODEL in fallbacks:
                idx = fallbacks.index(config.STT_MODEL)
                if idx + 1 < len(fallbacks):
                    new_model = fallbacks[idx + 1]
                    logger.warning(
                        "STT rate limit reached for %s. Auto-switching to %s",
                        config.STT_MODEL,
                        new_model,
                    )
                    config.STT_MODEL = new_model
        raise exc


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """
    Transcribe audio bytes to text using Groq Whisper.

    Args:
        audio_bytes: Raw audio data (WAV, MP3, WebM, OGG, M4A, FLAC).
        filename:    Hint for the file extension so Groq picks the right decoder.

    Returns:
        Transcript string (stripped of leading/trailing whitespace).

    Raises:
        RuntimeError: On API failure.
    """
    # Wrap bytes in a file-like object — Groq SDK expects a tuple or file path
    audio_file = (filename, io.BytesIO(audio_bytes), _mime_type(filename))

    try:
        transcript = _call_stt(audio_file, config.STT_LANGUAGE)
        logger.info("STT | transcript length=%d", len(transcript))
        return transcript

    except Exception as exc:
        logger.error("STT | Groq Whisper failed: %s", exc)
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
