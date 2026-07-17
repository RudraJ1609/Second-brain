"""
Shared configuration for SecondSelf.

Centralizes paths, model names, thresholds, and API secrets so every pipeline
script (capture, classify, link, build_graph, ask, app) imports from one place.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project roots
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

RAW_DIR = PROJECT_ROOT / "raw"
WIKI_DIR = PROJECT_ROOT / "wiki"
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"

GRAPH_PATH = DATA_DIR / "graph.json"
EMBEDDINGS_PATH = DATA_DIR / "embeddings.npz"

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# Thresholds / knobs
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.60"))
MAX_LINKS = int(os.getenv("MAX_LINKS", "5"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))

# Soft limits used by later phases (capture / classify truncation)
MAX_CAPTURE_CHARS = int(os.getenv("MAX_CAPTURE_CHARS", "100000"))
MAX_LLM_INPUT_CHARS = int(os.getenv("MAX_LLM_INPUT_CHARS", "12000"))
CONTENT_PREVIEW_CHARS = int(os.getenv("CONTENT_PREVIEW_CHARS", "200"))

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ---------------------------------------------------------------------------
# PARA categories (canonical set for classify)
# ---------------------------------------------------------------------------

PARA_CATEGORIES = ("Projects", "Areas", "Resources", "Archives")


def ensure_directories() -> None:
    """Create required folders if they do not exist."""
    for path in (RAW_DIR, WIKI_DIR, DATA_DIR, STATIC_DIR):
        path.mkdir(parents=True, exist_ok=True)


def validate_config() -> list[str]:
    """
    Return a list of configuration problems (empty if OK).

    Does not raise — callers decide whether to fail hard.
    """
    problems: list[str] = []

    if not (0.0 <= SIMILARITY_THRESHOLD <= 1.0):
        problems.append(
            f"SIMILARITY_THRESHOLD must be in [0, 1], got {SIMILARITY_THRESHOLD}"
        )
    if MAX_LINKS < 0:
        problems.append(f"MAX_LINKS must be >= 0, got {MAX_LINKS}")
    if RAG_TOP_K < 1:
        problems.append(f"RAG_TOP_K must be >= 1, got {RAG_TOP_K}")

    return problems


# Ensure folders exist on import so scripts can assume they are present.
ensure_directories()
