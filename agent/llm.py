"""
LLM client using Groq's OpenAI-compatible API.
Sends the assembled prompt and returns a parsed structured response.
Supports multi-turn conversation history.
"""

import json
import logging
import re
from typing import Any

from groq import Groq
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config
from agent.prompt import build_system_prompt, format_products_for_prompt

logger = logging.getLogger(__name__)

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


# Response schema

DEFAULT_RESPONSE: dict[str, Any] = {
    "response_text": "I'm sorry, I couldn't process that request. Please try again.",
    "intent": "unknown",
    "confidence": 0.0,
    "ui_actions": [],
}


# LLM call with retry


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_llm(system_prompt: str, messages: list[dict]) -> str:
    """Call Groq LLM with full conversation history and return raw response string."""
    client = _get_client()

    try:
        completion = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS,
            response_format={"type": "json_object"},  # enforce JSON output
        )
        return completion.choices[0].message.content or ""
    except Exception as exc:
        import groq

        if isinstance(exc, groq.RateLimitError) or (
            hasattr(exc, "status_code") and exc.status_code == 429
        ):
            fallbacks = [
                "llama-3.3-70b-versatile",
                "llama-3.1-8b-instant",
                "mixtral-8x7b-32768",
                "gemma2-9b-it",
            ]
            if config.LLM_MODEL in fallbacks:
                idx = fallbacks.index(config.LLM_MODEL)
                if idx + 1 < len(fallbacks):
                    new_model = fallbacks[idx + 1]
                    logger.warning(
                        "LLM rate limit reached for %s. Auto-switching to %s",
                        config.LLM_MODEL,
                        new_model,
                    )
                    config.LLM_MODEL = new_model
        raise exc


# Public API


def generate_response(
    user_message: str,
    retrieved_products: list[dict],
    conversation_history: list[dict] | None = None,
    price_constraints: dict | None = None,
    cart_context: str = "",
    profile_context: str = "",
) -> dict[str, Any]:
    """
    Run the LLM agent with the user message, product context, and conversation history.

    Args:
        user_message:           Transcript from STT (already sanitised).
        retrieved_products:     Product dicts from RAG retrieval.
        conversation_history:   List of previous turns.
        price_constraints:      Optional price filter dict.
        cart_context:           Formatted string of current cart items.
        profile_context:        Formatted string of user profile data.

    Returns:
        Parsed dict with keys: response_text, intent, confidence, ui_actions.
    """
    product_context = format_products_for_prompt(retrieved_products, price_constraints)
    system_prompt = build_system_prompt(product_context, cart_context, profile_context)

    logger.info(
        "LLM | model=%s | user=%r | products=%d | history=%d",
        config.LLM_MODEL,
        user_message[:80],
        len(retrieved_products),
        len(conversation_history) if conversation_history else 0,
    )

    # Build messages array with history + current user message
    messages: list[dict] = []

    if conversation_history:
        # Keep last N turns to avoid token overflow (each turn = 2 messages)
        max_history_turns = 6
        history_to_use = _sanitize_history(conversation_history)[
            -(max_history_turns * 2) :
        ]
        messages.extend(history_to_use)

    # Add current user message
    messages.append({"role": "user", "content": user_message})

    try:
        raw = _call_llm(system_prompt, messages)
        logger.debug("LLM | raw response: %s", raw[:300])
        result = _parse_response(raw)
        logger.info(
            "LLM | intent=%s confidence=%.2f actions=%d",
            result.get("intent"),
            result.get("confidence", 0),
            len(result.get("ui_actions", [])),
        )
        return result

    except Exception as exc:
        logger.error("LLM | Failed after retries: %s", exc)
        return DEFAULT_RESPONSE.copy()


# Response parsing


def _parse_response(raw: str) -> dict[str, Any]:
    """
    Parse the LLM's JSON response into a clean dict.
    Handles common LLM quirks like wrapping in markdown code blocks.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("LLM | JSON parse failed: %s | raw: %r", exc, raw[:200])
        # Attempt to extract JSON object from anywhere in the string
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return DEFAULT_RESPONSE.copy()
        else:
            return DEFAULT_RESPONSE.copy()

    # Normalise and validate required fields
    return {
        "response_text": str(
            data.get("response_text", DEFAULT_RESPONSE["response_text"])
        ),
        "intent": str(data.get("intent", "unknown")),
        "confidence": float(data.get("confidence", 0.0)),
        "ui_actions": _normalise_actions(data.get("ui_actions", [])),
    }


def _normalise_actions(actions: Any) -> list[dict]:
    """Ensure ui_actions is a list of dicts with 'action' and 'params' keys."""
    if not isinstance(actions, list):
        return []
    result = []
    for item in actions:
        if not isinstance(item, dict):
            continue
        action_type = str(item.get("action", "")).upper()
        params = item.get("params", {})
        if not isinstance(params, dict):
            params = {}
        if action_type:
            result.append({"action": action_type, "params": params})
    return result


def _sanitize_history(history: list[dict]) -> list[dict[str, str]]:
    """Keep only safe chat roles/content before sending history to the model."""
    clean = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            clean.append(
                {"role": role, "content": content[: config.MAX_TRANSCRIPT_CHARS]}
            )
    return clean
