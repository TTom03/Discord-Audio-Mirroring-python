"""
config.py – Loads all settings from the .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return val


def _int(key: str) -> int:
    return int(_require(key))


BOT_TOKEN: str = _require("BOT_TOKEN")

SOURCE_GUILD_ID: int   = _int("SOURCE_GUILD_ID")
SOURCE_CHANNEL_ID: int = _int("SOURCE_CHANNEL_ID")
SOURCE_USER_ID: int    = _int("SOURCE_USER_ID")

TARGETS: list[dict] = [
    {
        "guild_id":   _int("TARGET_1_GUILD_ID"),
        "channel_id": _int("TARGET_1_CHANNEL_ID"),
    },
    {
        "guild_id":   _int("TARGET_2_GUILD_ID"),
        "channel_id": _int("TARGET_2_CHANNEL_ID"),
    },
    {
        "guild_id":   _int("TARGET_3_GUILD_ID"),
        "channel_id": _int("TARGET_3_CHANNEL_ID"),
    },
]

JITTER_BUFFER_FRAMES: int = int(os.getenv("JITTER_BUFFER_FRAMES", "2"))
MAX_QUEUE_FRAMES: int     = int(os.getenv("MAX_QUEUE_FRAMES", "100"))
