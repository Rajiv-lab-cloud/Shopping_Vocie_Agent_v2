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
        model = config.STT_MODEL
        request = {
            "model": model,
            "file": audio_file,
            "response_format": "text",
        }

        # The newer GPT-4o transcription models have a smaller parameter surface
        # than whisper-1. Keep optional Whisper-only hints off those requests.
        if model == "whisper-1":
            request["temperature"] = 0.0
        if model == "whisper-1" and language:
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
    filename, mime_type = _detect_audio_type(audio_bytes, filename)
    # Wrap bytes in a file-like object; the SDK accepts a tuple with filename and MIME type.
    audio_file = (filename, io.BytesIO(audio_bytes), mime_type)

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


def _detect_audio_type(audio_bytes: bytes, filename: str) -> tuple[str, str]:
    """Return a filename and MIME type that match the actual audio container."""
    header = audio_bytes[:16]
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio.webm", "audio/webm"
    if header.startswith(b"RIFF") and b"WAVE" in audio_bytes[:32]:
        return "audio.wav", "audio/wav"
    if header.startswith(b"OggS"):
        return "audio.ogg", "audio/ogg"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "audio.mp3", "audio/mpeg"
    if b"ftyp" in audio_bytes[:16]:
        return "audio.m4a", "audio/mp4"
    return filename, _mime_type(filename)
