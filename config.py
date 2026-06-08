"""
Central configuration — loads from .env or environment variables.
All modules import from here; never read os.environ directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")

# OpenAI
OPENAI_API_KEY: str = os.getenv(
    "OPENAI_API_KEY", os.getenv("GROQ_API_KEY", "")
)  # GROQ_API_KEY kept for transition compatibility

# Models
STT_MODEL: str = os.getenv("STT_MODEL", "whisper-1")
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "").strip()
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
TTS_MODEL: str = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE: str = os.getenv("TTS_VOICE", "alloy")

# RAG
EMBEDDING_MODEL: str = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "10"))
RAG_TOP_N: int = int(os.getenv("RAG_TOP_N", "3"))

# LLM
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.20"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))

# Server
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")

# Database
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "postgresql://shopbot:shopbot_password@localhost:5433/shopping_db"
)
BASE_DIR = Path(__file__).parent

# Guardrail Settings
MAX_TRANSCRIPT_CHARS: int = 2000
MAX_RESPONSE_CHARS: int = 3000
MAX_UI_ACTIONS: int = 5

# Valid UI Action Types
VALID_UI_ACTIONS = {
    "SHOW_PRODUCTS",
    "FILTER_PRODUCTS",
    "NAVIGATE_TO",
    "SORT_PRODUCTS",
    "ADD_TO_CART",
    "REMOVE_FROM_CART",
    "SHOW_PRODUCT_DETAIL",
    "CLEAR_FILTERS",
    "CLEAR_CART",
    "CHECKOUT",
    "UPDATE_CART_QUANTITY",
}
