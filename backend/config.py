"""
PulseOS Backend Configuration
==============================
Central place for all tuneable constants. Values can be overridden by
environment variables where noted.
"""
import os

# ---------------------------------------------------------------------------
# Network Simulation Parameters
# ---------------------------------------------------------------------------
MAP_WIDTH: int = int(os.environ.get("MAP_WIDTH", 1000))
MAP_HEIGHT: int = int(os.environ.get("MAP_HEIGHT", 1000))
NUM_TOWERS: int = int(os.environ.get("NUM_TOWERS", 100))
NUM_USERS: int = int(os.environ.get("NUM_USERS", 5000))
DEFAULT_TOWER_CAPACITY: int = int(os.environ.get("DEFAULT_TOWER_CAPACITY", 200))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URI: str = os.environ.get("DATABASE_URI", "sqlite:///pulseos.db")

# ---------------------------------------------------------------------------
# AI / LLM Integration  (extension point — populated when Gemini is wired in)
# ---------------------------------------------------------------------------
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

__all__ = [
    "MAP_WIDTH",
    "MAP_HEIGHT",
    "NUM_TOWERS",
    "NUM_USERS",
    "DEFAULT_TOWER_CAPACITY",
    "DATABASE_URI",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
]