"""
FastAPI application — Voice Shopping Agent API.

Endpoints:
  POST /v1/shop          Main pipeline: audio/text → ui_actions + voice response
  GET  /v1/products      List all products (for frontend sync)
  POST /v1/rebuild-index Admin: rebuild FAISS vector index
  GET  /health           Health check
"""

import json
import logging
import logging.config
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
from agent import orchestrator
from api.middleware import RequestTracingMiddleware
from api.models import (
    AddToCartRequest,
    CartItemResponse,
    CheckoutRequest,
    HealthResponse,
    ProductResponse,
    ShopResponse,
)
from db.database import (
    add_to_cart,
    clear_cart,
    get_all_products,
    get_cart_items,
    get_user_profile,
    init_db,
    remove_from_cart,
    update_user_profile,
)
from db.seed import seed as seed_db

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# Startup / Shutdown


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database, seed data, and build FAISS index on startup."""
    logger.info("🚀 Starting Voice Shopping Agent API…")

    # Ensure Postgres connection is valid
    # Init schema

    # Init schema
    init_db()

    # Seed if empty
    from db.database import get_db

    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) FROM products").fetchone()
        count = row["count"] if isinstance(row, dict) else row[0]
    if count == 0:
        logger.info("Database empty — seeding with sample products…")
        seed_db()

    from agent import prompt
    prompt.init_dynamic_prompt()

    # Preload RAG embedder and index into memory
    from agent import rag

    rag.preload()

    logger.info("✅ Startup complete. API ready.")
    yield

    logger.info("👋 Shutting down Voice Shopping Agent API.")


# App

app = FastAPI(
    title="Voice Shopping Agent API",
    description="Voice-enabled AI shopping assistant powered by OpenAI.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow all origins for demo; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS if config.CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestTracingMiddleware)


# Endpoints


@app.get("/health", response_model=HealthResponse, tags=["Utility"])
async def health():
    """Check API and model configuration health."""
    return HealthResponse(
        status="ok",
        models={
            "stt": config.STT_MODEL,
            "llm": config.LLM_MODEL,
            "tts": f"{config.TTS_MODEL} / {config.TTS_VOICE}",
            "embedding": config.EMBEDDING_MODEL,
        },
    )


@app.post("/v1/shop", response_model=ShopResponse, tags=["Shopping Agent"])
async def shop(
    audio: Optional[UploadFile] = File(
        None, description="Audio file (WAV, MP3, WebM, OGG)"
    ),
    text: Optional[str] = Form(
        None, description="Text input (for testing without audio)"
    ),
    skip_tts: bool = Form(False, description="Skip TTS to reduce latency (testing)"),
    conversation_history: Optional[str] = Form(
        None, description="JSON array of prior conversation turns"
    ),
):
    """
    **Main endpoint.** Send customer audio or text → receive UI actions + voice response.

    - **audio**: Upload a recorded audio clip of the customer's voice.
    - **text**: Alternatively, send plain text (useful for debugging).
    - **skip_tts**: Set to `true` to skip speech synthesis (faster, text-only response).

    Returns:
    - `transcript` — what the customer said
    - `response_text` — what ShopBot says back
    - `ui_actions` — list of website control commands for the frontend
    - `audio_b64` — base64-encoded WAV of the spoken response
    """
    if audio is None and (text is None or text.strip() == ""):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either an audio file or text input.",
        )

    audio_bytes: Optional[bytes] = None
    audio_filename = "audio.wav"

    if audio is not None:
        audio_bytes = await audio.read()
        audio_filename = audio.filename or "audio.wav"

        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

    parsed_history = _parse_conversation_history(conversation_history)

    result = orchestrator.run(
        audio_bytes=audio_bytes,
        text_input=text,
        audio_filename=audio_filename,
        skip_tts=skip_tts,
        conversation_history=parsed_history,
    )

    return ShopResponse(**result)


@app.post("/v1/shop/stream", tags=["Shopping Agent"])
async def shop_stream(
    audio: Optional[UploadFile] = File(
        None, description="Audio file (WAV, MP3, WebM, OGG)"
    ),
    text: Optional[str] = Form(
        None, description="Text input (for testing without audio)"
    ),
    skip_tts: bool = Form(False, description="Skip TTS to reduce latency (testing)"),
    conversation_history: Optional[str] = Form(
        None, description="JSON array of prior conversation turns"
    ),
):
    """
    **Streaming endpoint.** Send customer audio or text → receive SSE events for transcript, ui_actions, and audio.
    """
    if audio is None and (text is None or text.strip() == ""):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either an audio file or text input.",
        )

    audio_bytes: Optional[bytes] = None
    audio_filename = "audio.wav"

    if audio is not None:
        audio_bytes = await audio.read()
        audio_filename = audio.filename or "audio.wav"
        if len(audio_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

    parsed_history = _parse_conversation_history(conversation_history)

    def event_generator():
        for event in orchestrator.run_stream(
            audio_bytes=audio_bytes,
            text_input=text,
            audio_filename=audio_filename,
            skip_tts=skip_tts,
            conversation_history=parsed_history,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """Bi-directional WebSocket for real-time voice shopping."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            text_input = payload.get("text")
            audio_b64 = payload.get("audio_b64")
            audio_bytes = None
            if audio_b64:
                import base64
                audio_bytes = base64.b64decode(audio_b64)
            
            # For simplicity, we assume conversation history is passed per request
            # In a real app, we could manage it in memory or Postgres.
            raw_history = payload.get("conversation_history", [])
            parsed_history = _parse_conversation_history(json.dumps(raw_history))
            
            for event in orchestrator.run_stream(
                audio_bytes=audio_bytes,
                text_input=text_input,
                audio_filename="audio.wav",
                skip_tts=payload.get("skip_tts", False),
                conversation_history=parsed_history,
            ):
                await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")


def _parse_conversation_history(raw_history: Optional[str]) -> list[dict[str, str]]:
    """Parse and sanitise browser-provided chat history before LLM use."""
    if not raw_history:
        return []

    try:
        decoded = json.loads(raw_history)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []

    if not isinstance(decoded, list):
        return []

    clean_history: list[dict[str, str]] = []
    for item in decoded[-12:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue

        content = content.strip()
        if not content:
            continue

        clean_history.append(
            {
                "role": role,
                "content": content[: config.MAX_TRANSCRIPT_CHARS],
            }
        )

    return clean_history


@app.get("/v1/products", response_model=list[ProductResponse], tags=["Products"])
async def list_products(
    category: Optional[str] = None, limit: int = 50, offset: int = 0
):
    """
    Return active products in the catalog with pagination, optionally filtered by category.
    The frontend uses this to build its product grid dynamically.
    """
    try:
        if category:
            from db.database import get_products_by_category

            products = get_products_by_category(category, limit=limit)
        else:
            products = get_all_products(limit=limit, offset=offset)
        return [ProductResponse(**p) for p in products]
    except Exception as exc:
        logger.error("GET /v1/products failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch products.")


@app.get("/v1/products/by-ids", response_model=list[ProductResponse], tags=["Products"])
async def list_products_by_ids(ids: str):
    """Fetch specific products by a comma-separated list of IDs."""
    try:
        id_list = [int(i.strip()) for i in ids.split(",") if i.strip().isdigit()]
        from db.database import get_products_by_ids

        products = get_products_by_ids(id_list)
        return [ProductResponse(**p) for p in products]
    except Exception as exc:
        logger.error("GET /v1/products/by-ids failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch products by IDs.")


@app.get("/v1/categories", tags=["Products"])
async def list_categories():
    """Return all active category names and slugs from the database."""
    try:
        from db.database import get_db
        with get_db() as conn:
            rows = conn.execute("SELECT name, slug FROM categories ORDER BY name ASC").fetchall()
            return [{"name": r["name"], "slug": r["slug"]} for r in rows]
    except Exception as exc:
        logger.error("GET /v1/categories failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch categories.")


@app.get("/v1/cart", response_model=list[CartItemResponse], tags=["Cart"])
async def get_cart():
    """Return all items currently in the shopping cart."""
    try:
        items = get_cart_items()
        return [CartItemResponse(**item) for item in items]
    except Exception as exc:
        logger.error("GET /v1/cart failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch cart.")


@app.post("/v1/cart/add", tags=["Cart"])
async def api_add_to_cart(req: AddToCartRequest):
    """Add a product to the cart."""
    try:
        cart_id = add_to_cart(req.product_id, req.quantity)
        return {"status": "ok", "cart_id": cart_id}
    except Exception as exc:
        logger.error("POST /v1/cart/add failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to add to cart.")


@app.post("/v1/cart/update", tags=["Cart"])
async def api_update_cart(req: AddToCartRequest):
    """Update the quantity of a product in the cart."""
    try:
        from db.database import update_cart_quantity

        success = update_cart_quantity(req.product_id, req.quantity)
        if not success:
            raise HTTPException(status_code=404, detail="Product not found in cart.")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("POST /v1/cart/update failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update cart.")


@app.delete("/v1/cart/{cart_id}", tags=["Cart"])
async def api_remove_from_cart(cart_id: int):
    """Remove a product from the cart."""
    try:
        success = remove_from_cart(cart_id)
        if not success:
            raise HTTPException(status_code=404, detail="Item not found in cart.")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("DELETE /v1/cart/{cart_id} failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to remove from cart.")


@app.delete("/v1/cart", tags=["Cart"])
async def api_clear_cart():
    """Clear the entire shopping cart."""
    try:
        clear_cart()
        return {"status": "ok"}
    except Exception as exc:
        logger.error("DELETE /v1/cart failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to clear cart.")


@app.post("/v1/cart/checkout", tags=["Cart"])
async def api_checkout_cart(req: CheckoutRequest):
    """Generate a PDF bill and clear the cart."""
    try:
        items = get_cart_items()
        if not items:
            raise HTTPException(status_code=400, detail="Cart is empty.")

        profile = get_user_profile()
        final_address = profile.get("address")
        final_payment = profile.get("payment_method")

        # If new details provided and they aren't default "N/A", save them
        if req.address and req.address != "N/A" and req.address != "Not Provided":
            final_address = req.address
        if (
            req.payment_method
            and req.payment_method != "N/A"
            and req.payment_method != "Not Provided"
        ):
            final_payment = req.payment_method

        # Default fallbacks
        final_address = final_address or "Not Provided"
        final_payment = final_payment or "Not Provided"

        # Update profile to persist
        update_user_profile(final_address, final_payment)

        import io

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18,
        )
        styles = getSampleStyleSheet()
        elements = []

        # Custom styles
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Heading1"],
            fontSize=24,
            spaceAfter=12,
            textColor=colors.HexColor("#2c3e50"),
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontSize=12,
            spaceAfter=20,
            textColor=colors.HexColor("#7f8c8d"),
        )

        # Header
        elements.append(Paragraph("<b>AI-KART INVOICE</b>", title_style))
        elements.append(
            Paragraph("Thank you for your futuristic purchase!", subtitle_style)
        )
        elements.append(Spacer(1, 12))

        # Customer Info
        elements.append(
            Paragraph(f"<b>Delivery Address:</b> {final_address}", styles["Normal"])
        )
        elements.append(
            Paragraph(f"<b>Payment Method:</b> {final_payment}", styles["Normal"])
        )
        elements.append(Spacer(1, 24))

        # Items Table
        data = [["Item", "Unit Price", "Qty", "Total"]]
        total_amount = 0

        for item in items:
            item_total = item["price"] * item["quantity"]
            total_amount += item_total
            data.append(
                [
                    item["name"][:40] + ("..." if len(item["name"]) > 40 else ""),
                    f"INR {item['price']:.2f}",
                    str(item["quantity"]),
                    f"INR {item_total:.2f}",
                ]
            )

        data.append(["", "", "Grand Total:", f"INR {total_amount:.2f}"])

        t = Table(data, colWidths=[250, 80, 50, 90])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3498db")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -2), colors.HexColor("#f7f9f9")),
                    ("GRID", (0, 0), (-1, -2), 1, colors.HexColor("#ecf0f1")),
                    ("FONTNAME", (2, -1), (3, -1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (2, -1), (3, -1), colors.HexColor("#e74c3c")),
                    ("LINEABOVE", (2, -1), (3, -1), 2, colors.HexColor("#34495e")),
                ]
            )
        )

        elements.append(t)

        # Footer
        elements.append(Spacer(1, 48))
        elements.append(
            Paragraph(
                "<i>Your intelligent items will be dispatched shortly. Have a nice day!</i>",
                styles["Normal"],
            )
        )

        doc.build(elements)

        from db.database import checkout_cart
        checkout_cart()

        from fastapi import Response

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=bill.pdf"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("POST /v1/cart/checkout failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process checkout.")


# Static Files

# Serve new modular frontend as static files (Must be at the bottom to avoid catching API routes)
_frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dir.exists():
    app.mount(
        "/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend"
    )


# Entry point

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level="info",
    )
