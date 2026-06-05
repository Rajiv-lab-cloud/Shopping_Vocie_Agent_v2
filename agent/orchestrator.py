"""
Orchestrator — wires all pipeline stages together.

Pipeline:
  audio bytes
    → STT (Whisper via Groq)
    → Input Guardrails
    → RAG Retrieval (FAISS + SQLite)
    → LLM Agent (Groq llama-3.3-70b)
    → Output Guardrails
    → TTS (PlayAI via Groq)
    → structured response dict
"""

import json
import logging
import time
from typing import Any, Generator, Optional

from agent import guardrails, llm, rag, stt, tts
from agent.guardrails import InputGuardrailError, OutputGuardrailError
from agent.prompt import format_cart_for_prompt
from db.database import get_cart_items, get_user_profile, update_user_preferences

logger = logging.getLogger(__name__)


def print(*args, **kwargs):
    """Safely print to stdout, handling encoding issues on Windows."""
    import sys
    import builtins
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        sep = kwargs.get('sep', ' ')
        end = kwargs.get('end', '\n')
        file = kwargs.get('file', sys.stdout)
        
        text = sep.join(str(arg) for arg in args)
        encoding = getattr(file, 'encoding', 'utf-8') or 'utf-8'
        safe_text = text.encode(encoding, errors='replace').decode(encoding)
        
        file.write(safe_text + end)
        file.flush()


def run(
    audio_bytes: Optional[bytes] = None,
    text_input: Optional[str] = None,
    audio_filename: str = "audio.wav",
    skip_tts: bool = False,
    conversation_history: Optional[list] = None,
) -> dict[str, Any]:
    """
    Run the full voice shopping pipeline.

    Args:
        audio_bytes:            Raw audio bytes (mutually exclusive with text_input).
        text_input:             Plain text transcript (for testing without audio).
        audio_filename:         Filename hint for MIME type detection.
        skip_tts:               If True, skip TTS synthesis (returns empty audio_b64).
        conversation_history:   List of prior turns for multi-turn conversation context.

    Returns:
        Dict with keys:
            transcript    (str)  — what the customer said
            response_text (str)  — what the assistant says back
            intent        (str)  — detected intent
            confidence    (float)
            ui_actions    (list) — website control commands
            audio_b64     (str)  — base64-encoded WAV (empty if skip_tts=True)
            latency_ms    (dict) — per-stage timing for observability
    """
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    # Stage 1: Speech-to-Text
    if text_input:
        transcript = text_input
        timings["stt_ms"] = 0
    elif audio_bytes:
        t = time.perf_counter()
        try:
            transcript = stt.transcribe(audio_bytes, audio_filename)
        except RuntimeError as exc:
            return _error_response(str(exc), timings)
        timings["stt_ms"] = _ms(t)
    else:
        return _error_response("No audio or text input provided.", timings)

    logger.info("PIPELINE | transcript: %r", transcript[:120])
    print(f"\n{'=' * 60}")
    print(f'🎤 STT HEARD: "{transcript}"')
    print(f"{'=' * 60}")

    # Stage 2: Input Guardrails
    t = time.perf_counter()
    try:
        safe_transcript = guardrails.validate_input(transcript)
    except InputGuardrailError as exc:
        return _guardrail_response(str(exc), transcript, skip_tts, timings)
    timings["guardrail_input_ms"] = _ms(t)

    # Stage 3: RAG Retrieval
    t = time.perf_counter()
    try:
        profile = get_user_profile()
        prefs = profile.get("preferences")
        rag_query = safe_transcript
        if prefs:
            rag_query = f"{safe_transcript} (User preferences: {prefs})"
            
        # Extract price constraints once, reuse for RAG filter + LLM prompt
        price_constraints = rag.extract_price_constraints(rag_query)
        retrieved_products = rag.retrieve(
            rag_query, price_constraints=price_constraints
        )
    except Exception as exc:
        logger.error("PIPELINE | RAG failed: %s", exc)
        retrieved_products = []  # Degrade gracefully — LLM can still respond
        price_constraints = {}
    timings["rag_ms"] = _ms(t)

    logger.info(
        "PIPELINE | RAG returned %d products (price_filter=%s)",
        len(retrieved_products),
        price_constraints or "none",
    )
    print(f"🔍 RAG FOUND: {len(retrieved_products)} products")
    if price_constraints:
        print(f"   💰 Price filter active: {price_constraints}")
    for i, p in enumerate(retrieved_products[:5]):
        print(
            f"   [{i + 1}] id={p.get('id')} | {p.get('name', '?')[:50]} | ₹{p.get('price', '?')}"
        )

    # Stage 4: LLM Agent
    t = time.perf_counter()
    cart_context = format_cart_for_prompt(get_cart_items())

    profile = get_user_profile()
    profile_context = f"Address: {profile.get('address') or 'None'} | Payment Method: {profile.get('payment_method') or 'None'} | Preferences: {profile.get('preferences') or 'None'}"

    llm_response = llm.generate_response(
        safe_transcript,
        retrieved_products,
        conversation_history=conversation_history or [],
        price_constraints=price_constraints,
        cart_context=cart_context,
        profile_context=profile_context,
    )

    if not retrieved_products and llm_response.get("intent") == "product_search":
        llm_response["ui_actions"] = []
        llm_response["intent"] = "out_of_stock"

    if llm_response.get("intent") == "out_of_stock":
        llm_response["ui_actions"] = []

    if llm_response.get("intent") == "error" and retrieved_products:
        logger.info(
            "PIPELINE | LLM failed, falling back to local FAISS search results."
        )
        llm_response = {
            "response_text": f"I had trouble processing that, but I found {len(retrieved_products)} products matching your search.",
            "intent": "search_fallback",
            "confidence": 1.0,
            "ui_actions": [
                {
                    "action": "SHOW_PRODUCTS",
                    "params": {"product_ids": [p["id"] for p in retrieved_products]},
                }
            ],
        }
    
    for action in llm_response.get("ui_actions", []):
        if action.get("action") == "UPDATE_PREFERENCES":
            prefs = action.get("params", {}).get("preferences")
            if prefs:
                update_user_preferences(prefs)

    timings["llm_ms"] = _ms(t)

    # Stage 5: Output Guardrails
    t = time.perf_counter()
    try:
        allowed_product_ids = [p["id"] for p in retrieved_products]
        
        orig_actions = [
            a.get("action")
            for a in llm_response.get("ui_actions", [])
            if isinstance(a, dict)
        ]
        
        validated = guardrails.validate_output(llm_response, allowed_product_ids)

        # Check if the LLM hallucinated fake product IDs and they were all blocked
        val_actions = [a.get("action") for a in validated.get("ui_actions", [])]
        if "SHOW_PRODUCTS" in orig_actions and "SHOW_PRODUCTS" not in val_actions:
            logger.warning(
                "PIPELINE | Detected LLM hallucination: SHOW_PRODUCTS was completely blocked. Overriding response."
            )
            validated["intent"] = "out_of_stock"
            validated["ui_actions"] = []
            validated["response_text"] = (
                "I'm sorry, I couldn't find any products matching your request in our current inventory."
            )

    except OutputGuardrailError as exc:
        logger.error("PIPELINE | Output guardrail blocked response: %s", exc)
        validated = {
            "response_text": "Whoops! Looks like I got my shopping bags in a twist. How can I help you find what you need?",
            "intent": "blocked",
            "confidence": 1.0,
            "ui_actions": [],
        }
    timings["guardrail_output_ms"] = _ms(t)

    print(f'🧠 LLM RESPONSE: "{validated["response_text"][:150]}"')
    print(
        f"   Intent: {validated.get('intent', '?')} | Confidence: {validated.get('confidence', '?')}"
    )
    print(f"   UI Actions: {validated.get('ui_actions', [])}")

    # Stage 6: Text-to-Speech
    audio_b64 = ""
    if not skip_tts:
        t = time.perf_counter()
        try:
            audio_b64 = tts.synthesize_b64(validated["response_text"])
        except RuntimeError as exc:
            logger.error("PIPELINE | TTS failed: %s — continuing without audio.", exc)
        timings["tts_ms"] = _ms(t)

    timings["total_ms"] = _ms(t0)
    logger.info("PIPELINE | Done in %.0fms", timings["total_ms"])
    print(
        f"🔊 TTS: {'Generated audio' if audio_b64 else 'No audio (failed or skipped)'}"
    )
    print(f"⏱️  Total: {timings['total_ms']:.0f}ms")
    print(f"{'=' * 60}\n")

    return {
        "transcript": transcript,
        "response_text": validated["response_text"],
        "intent": validated.get("intent", "unknown"),
        "confidence": validated.get("confidence", 0.0),
        "ui_actions": validated.get("ui_actions", []),
        "audio_b64": audio_b64,
        "latency_ms": timings,
    }


def run_stream(
    audio_bytes: Optional[bytes] = None,
    text_input: Optional[str] = None,
    audio_filename: str = "audio.wav",
    skip_tts: bool = False,
    conversation_history: Optional[list] = None,
) -> Generator[str, None, None]:
    """
    Generator that yields JSON strings for Server-Sent Events.
    Events:
      - transcript: { "transcript": str }
      - actions: { "ui_actions": list }
      - audio: { "audio_b64": str, "response_text": str }
      - error: { "error": str }
    """
    # Stage 1: STT
    if text_input:
        transcript = text_input
    elif audio_bytes:
        try:
            transcript = stt.transcribe(audio_bytes, audio_filename)
        except RuntimeError as exc:
            yield {"event": "error", "data": {"error": str(exc)}}
            return
    else:
        yield {"event": "error", "data": {"error": "No audio or text input provided."}}
        return

    yield {"event": "transcript", "data": {"transcript": transcript}}

    # Stage 2: Input Guardrails
    try:
        safe_transcript = guardrails.validate_input(transcript)
    except InputGuardrailError as exc:
        msg = str(exc)
        yield {"event": "actions", "data": {"ui_actions": []}}

        audio_b64 = ""
        if not skip_tts:
            try:
                audio_b64 = tts.synthesize_b64(msg)
            except Exception:
                pass
        yield {"event": "audio", "data": {"response_text": msg, "audio_b64": audio_b64}}
        return

    # Stage 3: RAG
    try:
        profile = get_user_profile()
        prefs = profile.get("preferences")
        rag_query = safe_transcript
        if prefs:
            rag_query = f"{safe_transcript} (User preferences: {prefs})"
            
        price_constraints = rag.extract_price_constraints(rag_query)
        retrieved_products = rag.retrieve(
            rag_query, price_constraints=price_constraints
        )
    except Exception as exc:
        logger.error("PIPELINE | RAG failed: %s", exc)
        retrieved_products = []
        price_constraints = {}

    # Stage 4: LLM
    profile = get_user_profile()
    profile_context = f"Address: {profile.get('address') or 'None'} | Payment Method: {profile.get('payment_method') or 'None'} | Preferences: {profile.get('preferences') or 'None'}"
    
    cart_context = format_cart_for_prompt(get_cart_items())
    llm_response = llm.generate_response(
        safe_transcript,
        retrieved_products,
        conversation_history=conversation_history or [],
        price_constraints=price_constraints,
        cart_context=cart_context,
        profile_context=profile_context,
    )

    # If the LLM tried to search for products but we found none, it shouldn't filter the UI
    # This prevents the 8B model from randomly filtering to "Groceries" when asked for "Snacks" (which we don't have)
    if not retrieved_products and llm_response.get("intent") == "product_search":
        llm_response["ui_actions"] = []
        llm_response["intent"] = "out_of_stock"

    if llm_response.get("intent") == "out_of_stock":
        llm_response["ui_actions"] = []

    if llm_response.get("intent") == "error" and retrieved_products:
        logger.info(
            "PIPELINE | LLM failed, falling back to local FAISS search results."
        )
        llm_response = {
            "response_text": f"I had trouble processing that, but I found {len(retrieved_products)} products matching your search.",
            "intent": "search_fallback",
            "confidence": 1.0,
            "ui_actions": [
                {
                    "action": "SHOW_PRODUCTS",
                    "params": {"product_ids": [p["id"] for p in retrieved_products]},
                }
            ],
        }

    for action in llm_response.get("ui_actions", []):
        if action.get("action") == "UPDATE_PREFERENCES":
            prefs = action.get("params", {}).get("preferences")
            if prefs:
                update_user_preferences(prefs)

    # Stage 5: Output Guardrails
    try:
        allowed_product_ids = [p["id"] for p in retrieved_products]
        
        orig_actions = [
            a.get("action")
            for a in llm_response.get("ui_actions", [])
            if isinstance(a, dict)
        ]
        
        validated = guardrails.validate_output(llm_response, allowed_product_ids)

        # Check if the LLM hallucinated fake product IDs and they were all blocked
        val_actions = [a.get("action") for a in validated.get("ui_actions", [])]
        if "SHOW_PRODUCTS" in orig_actions and "SHOW_PRODUCTS" not in val_actions:
            logger.warning(
                "PIPELINE | Detected LLM hallucination: SHOW_PRODUCTS was completely blocked. Overriding response."
            )
            validated["intent"] = "out_of_stock"
            validated["ui_actions"] = []
            validated["response_text"] = (
                "I'm sorry, I couldn't find any products matching your request in our current inventory."
            )

    except OutputGuardrailError as exc:
        logger.error("PIPELINE | Output guardrail blocked response: %s", exc)
        validated = {
            "response_text": "I'm sorry, I can't respond to that. How can I help you shop?",
            "intent": "blocked",
            "confidence": 1.0,
            "ui_actions": [],
        }

    # Yield actions so UI can update immediately
    yield {"event": "actions", "data": {"ui_actions": validated.get("ui_actions", [])}}

    # Stage 6: TTS
    audio_b64 = ""
    if not skip_tts:
        try:
            audio_b64 = tts.synthesize_b64(validated["response_text"])
        except RuntimeError as exc:
            logger.error("PIPELINE | TTS failed: %s — continuing without audio.", exc)

    # Yield audio
    yield {
        "event": "audio",
        "data": {
            "response_text": validated["response_text"],
            "audio_b64": audio_b64,
        },
    }


# Helpers


def _ms(since: float) -> float:
    return round((time.perf_counter() - since) * 1000, 1)


def _error_response(message: str, timings: dict) -> dict[str, Any]:
    return {
        "transcript": "",
        "response_text": message,
        "intent": "error",
        "confidence": 0.0,
        "ui_actions": [],
        "audio_b64": "",
        "latency_ms": timings,
    }


def _guardrail_response(
    message: str,
    transcript: str,
    skip_tts: bool,
    timings: dict,
) -> dict[str, Any]:
    """Return a guardrail rejection response with TTS if requested."""
    audio_b64 = ""
    if not skip_tts:
        try:
            audio_b64 = tts.synthesize_b64(message)
        except Exception:
            pass
    return {
        "transcript": transcript,
        "response_text": message,
        "intent": "blocked",
        "confidence": 1.0,
        "ui_actions": [],
        "audio_b64": audio_b64,
        "latency_ms": timings,
    }
