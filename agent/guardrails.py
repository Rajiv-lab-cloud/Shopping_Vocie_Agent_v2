"""
Safety guardrails for input and output validation.

Input guardrails:  Applied to raw STT transcript before LLM call.
Output guardrails: Applied to LLM response before returning to client.
"""

import logging
import re
from typing import Any

import config
from db.database import product_exists

logger = logging.getLogger(__name__)

_VALID_NAV_PAGES = {
    "home",
    "cart",
    "checkout",
    "category/beauty",
    "category/fragrances",
    "category/furniture",
    "category/groceries",
}

_VALID_SORTS = {"price_asc", "price_desc", "rating", "newest"}
_VALID_FILTER_KEYS = {
    "category",
    "color",
    "max_price",
    "min_price",
    "min_rating",
    "brand",
    "tags",
}


# Prompt Injection Patterns

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"forget\s+(everything|all|your\s+instructions?)",
    r"you\s+are\s+now\s+(a|an)\s+\w+",
    r"act\s+as\s+(if\s+you\s+are|a|an)",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"dan\s+mode",
    r"developer\s+mode",
    r"override\s+(system|instructions?|prompt)",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"show\s+(me\s+)?(your\s+)?(instructions?|prompt|rules)",
    r"disregard\s+(all\s+)?(previous|prior)",
]

_COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


# Offensive Content Patterns

_OFFENSIVE_WORDS = [
    "fuck",
    "shit",
    "bitch",
    "asshole",
    "bastard",
    "dick",
    "pussy",
    "cunt",
    "nigger",
    "faggot",
    "retard",
]

_OFFENSIVE_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in _OFFENSIVE_WORDS) + r")\b",
    re.IGNORECASE,
)


# PII Patterns
_PII_PATTERNS = [
    (re.compile(r"\b\d{10}\b"), "[PHONE]"),
    (re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"), "[EMAIL]"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# INPUT GUARDRAILS
# ═══════════════════════════════════════════════════════════════════════════════


class InputGuardrailError(Exception):
    """Raised when the input fails safety checks."""

    pass


def validate_input(transcript: str) -> str:
    """
    Run all input safety checks on a raw transcript.

    Args:
        transcript: Raw text from STT.

    Returns:
        Sanitised transcript (PII redacted).

    Raises:
        InputGuardrailError: If the input is unsafe.
    """
    if not transcript or not transcript.strip():
        raise InputGuardrailError("Empty transcript received.")

    # Length check
    if len(transcript) > config.MAX_TRANSCRIPT_CHARS:
        logger.warning(
            "Guardrail | Transcript too long (%d chars), truncating.", len(transcript)
        )
        transcript = transcript[: config.MAX_TRANSCRIPT_CHARS]

    # Prompt injection detection
    for pattern in _COMPILED_INJECTION:
        if pattern.search(transcript):
            logger.warning(
                "Guardrail | Prompt injection detected: %r", transcript[:100]
            )
            raise InputGuardrailError(
                "Whoops! I'm just a simple shopping bot, so I can't do that. But I can definitely help you find some amazing deals on our store!"
            )

    # Offensive input
    if _OFFENSIVE_PATTERN.search(transcript):
        logger.warning("Guardrail | Offensive input detected.")
        raise InputGuardrailError(
            "Let's keep things family-friendly while we shop! 😊 What were you looking to buy today?"
        )

    # Redact PII
    for pattern, replacement in _PII_PATTERNS:
        transcript = pattern.sub(replacement, transcript)

    return transcript


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT GUARDRAILS
# ═══════════════════════════════════════════════════════════════════════════════


class OutputGuardrailError(Exception):
    """Raised when the LLM output fails safety checks."""

    pass


def validate_output(
    response: dict[str, Any], allowed_product_ids: list[int] | None = None
) -> dict[str, Any]:
    """
    Validate and sanitise the LLM's structured response.

    Args:
        response: Parsed LLM response dict.
        allowed_product_ids: Optional list of IDs that were in the LLM's RAG context.

    Returns:
        Validated (possibly modified) response dict.

    Raises:
        OutputGuardrailError: If the output is fundamentally unsafe.
    """
    # response_text checks
    response_text = str(response.get("response_text", ""))

    if not response_text.strip():
        response["response_text"] = (
            "I'm here to help! What would you like to shop for today?"
        )

    if len(response_text) > config.MAX_RESPONSE_CHARS:
        logger.warning("Guardrail | Response too long, truncating.")
        response["response_text"] = (
            response_text[: config.MAX_RESPONSE_CHARS - 3] + "..."
        )

    if _OFFENSIVE_PATTERN.search(response_text):
        logger.error("Guardrail | Offensive content in LLM response — blocking.")
        raise OutputGuardrailError("LLM generated offensive content.")

    # ui_actions checks
    actions = response.get("ui_actions", [])

    if not isinstance(actions, list):
        logger.warning("Guardrail | ui_actions is not a list — resetting.")
        response["ui_actions"] = []
        return response

    # Cap number of actions
    if len(actions) > config.MAX_UI_ACTIONS:
        logger.warning(
            "Guardrail | Too many UI actions (%d), capping at %d.",
            len(actions),
            config.MAX_UI_ACTIONS,
        )
        actions = actions[: config.MAX_UI_ACTIONS]

    validated_actions = []
    for action in actions:
        if not isinstance(action, dict):
            continue

        action_type = str(action.get("action", "")).upper()
        params = action.get("params", {})
        if not isinstance(params, dict):
            logger.warning(
                "Guardrail | Params for %s are not an object - skipping.", action_type
            )
            continue

        # Alias common hallucinated actions
        if action_type == "SHOW_CART":
            action_type = "NAVIGATE_TO"
            params = {"page": "cart"}

        # Action type whitelist
        if action_type not in config.VALID_UI_ACTIONS:
            logger.warning(
                "Guardrail | Unknown UI action type: %r — skipping.", action_type
            )
            continue

        # Validate product IDs exist in DB (prevent hallucinated products)
        if action_type in (
            "SHOW_PRODUCTS",
            "SHOW_PRODUCT_DETAIL",
            "ADD_TO_CART",
            "REMOVE_FROM_CART",
        ):
            params = _validate_product_ids(action_type, params, allowed_product_ids)
            if params is None:
                continue

        # Validate price ranges make sense
        if action_type == "FILTER_PRODUCTS":
            params = _validate_filter_params(params)
            if not params:
                continue

        if action_type == "NAVIGATE_TO":
            params = _validate_navigation_params(params)
            if params is None:
                continue

        if action_type == "SORT_PRODUCTS":
            params = _validate_sort_params(params)
            if params is None:
                continue

        if action_type == "CLEAR_FILTERS":
            params = {}

        if action_type == "CLEAR_CART":
            params = {}

        validated_actions.append({"action": action_type, "params": params})

    response["ui_actions"] = validated_actions
    return response


def _validate_product_ids(
    action_type: str, params: dict, allowed_product_ids: list[int] | None = None
) -> dict | None:
    """Validate product actions and drop commands that target missing products."""
    if action_type == "SHOW_PRODUCTS":
        raw_ids = params.get("product_ids", [])
        if not isinstance(raw_ids, list):
            logger.warning(
                "Guardrail | SHOW_PRODUCTS product_ids is not a list - skipping."
            )
            return None

        valid_ids = []
        for raw_id in raw_ids:
            pid = _coerce_product_id(raw_id)
            if pid is not None and product_exists(pid):
                # If we have strict allowed IDs from RAG, ensure the ID was actually shown to the LLM
                if allowed_product_ids is not None and pid not in allowed_product_ids:
                    continue
                valid_ids.append(pid)

        if len(valid_ids) != len(raw_ids):
            logger.warning(
                "Guardrail | Removed %d invalid product IDs from SHOW_PRODUCTS.",
                len(raw_ids) - len(valid_ids),
            )
        if not valid_ids:
            return None
        return {"product_ids": valid_ids}

    if action_type in (
        "SHOW_PRODUCT_DETAIL",
        "ADD_TO_CART",
        "REMOVE_FROM_CART",
        "UPDATE_CART_QUANTITY",
    ):
        pid = _coerce_product_id(params.get("product_id"))
        if pid is None or not product_exists(pid):
            logger.warning(
                "Guardrail | product_id=%r is invalid - removing action.",
                params.get("product_id"),
            )
            return None

        result = {"product_id": pid}
        if (
            action_type in ("ADD_TO_CART", "UPDATE_CART_QUANTITY")
            and "quantity" in params
        ):
            try:
                result["quantity"] = int(params["quantity"])
            except (ValueError, TypeError):
                pass
        return result

    return params


def _validate_filter_params(params: dict) -> dict:
    """Sanitise filter parameters and drop unsupported keys."""
    params = dict(params)

    # Drop any keys not in the whitelist
    for key in list(params.keys()):
        if key not in _VALID_FILTER_KEYS:
            del params[key]

    for key in ("max_price", "min_price"):
        val = params.get(key)
        if val is not None:
            try:
                params[key] = max(0.0, float(val))
            except (TypeError, ValueError):
                del params[key]

    if "min_rating" in params:
        try:
            params["min_rating"] = max(0.0, min(5.0, float(params["min_rating"])))
        except (TypeError, ValueError):
            del params["min_rating"]

    return params


def _validate_navigation_params(params: dict) -> dict | None:
    """Validate navigation targets for the frontend router."""
    page = str(params.get("page", "")).strip().lower()
    if page in ("home", "cart", "checkout") or page.startswith("category/"):
        return {"page": page}
    logger.warning("Guardrail | Invalid navigation page: %r - skipping.", page)
    return None


def _validate_sort_params(params: dict) -> dict | None:
    """Validate supported product sort options."""
    sort_by = str(params.get("sort_by", "")).strip().lower()
    if sort_by not in _VALID_SORTS:
        logger.warning("Guardrail | Invalid sort option: %r - skipping.", sort_by)
        return None
    return {"sort_by": sort_by}


def _coerce_product_id(value: Any) -> int | None:
    """Return a positive integer product ID, or None for malformed values."""
    if isinstance(value, bool):
        return None
    try:
        pid = int(value)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None
