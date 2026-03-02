"""
bot.py – Voice Bridge bot (no commands).

Behaviour:
  - On ready: check if the monitored user is already in the source channel.
    If yes → start bridge immediately.
    If no  → wait silently until they join.
  - On voice state update: start bridge when user joins source channel,
    stop bridge when user leaves.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

import discord

import config
from audio_bridge import AudioBridge

# ─────────────────────────────────────────────────────────────────────────────
#  Logging with rotation
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger("voice_bridge")
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console_handler.setFormatter(console_fmt)
logger.addHandler(console_handler)

# File handler with rotation (10 MB max, keep 5 backups)
file_handler = RotatingFileHandler(
    "voice_bridge.log",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,
    encoding="utf-8",
)
file_handler.setLevel(logging.DEBUG)
file_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler.setFormatter(file_fmt)
logger.addHandler(file_handler)

# Suppress verbose library logs
logging.getLogger("discord.opus").setLevel(logging.ERROR)
logging.getLogger("discord.voice_client").setLevel(logging.WARNING)
# Suppress py-cord's Opus decoding warnings (normal on startup/jitter)
logging.getLogger("discord").setLevel(logging.ERROR)

# ─────────────────────────────────────────────────────────────────────────────
#  Bot setup
# ─────────────────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.voice_states = True
intents.guilds       = True

bot = discord.Bot(intents=intents)

bridge: AudioBridge = AudioBridge(
    bot=bot,
    source_guild_id      = config.SOURCE_GUILD_ID,
    source_channel_id    = config.SOURCE_CHANNEL_ID,
    source_user_id       = config.SOURCE_USER_ID,
    targets              = config.TARGETS,
    jitter_buffer_frames = config.JITTER_BUFFER_FRAMES,
    max_queue_frames     = config.MAX_QUEUE_FRAMES,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────────────────────────────────────

async def _user_in_source_channel() -> bool:
    """
    Fetch the monitored user directly from the API (bypasses cache)
    and check whether they are in the source voice channel.
    """
    guild = bot.get_guild(config.SOURCE_GUILD_ID)
    if guild is None:
        logger.warning("_user_check: source guild %d not found", config.SOURCE_GUILD_ID)
        return False
    try:
        member = await guild.fetch_member(config.SOURCE_USER_ID)
    except discord.NotFound:
        logger.warning("_user_check: user %d not found in guild", config.SOURCE_USER_ID)
        return False
    except Exception as exc:
        logger.warning("_user_check: fetch_member failed: %s", exc)
        return False

    if member.voice is None or member.voice.channel is None:
        logger.info("_user_check: user %d is not in any voice channel", config.SOURCE_USER_ID)
        return False

    logger.info(
        "_user_check: user %d is in channel '%s' (id=%d)",
        config.SOURCE_USER_ID, member.voice.channel.name, member.voice.channel.id,
    )
    return member.voice.channel.id == config.SOURCE_CHANNEL_ID

# ─────────────────────────────────────────────────────────────────────────────
#  Events
# ─────────────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready() -> None:
    logger.info("Logged in as %s (id=%d)", bot.user, bot.user.id)
    guild_names = [g.name or f"(id={g.id})" for g in bot.guilds]
    logger.info("Connected to %d guild(s): %s", len(bot.guilds), ", ".join(guild_names))

    # Verify the bot is present in all required guilds
    required_ids = {config.SOURCE_GUILD_ID} | {t["guild_id"] for t in config.TARGETS}
    missing = required_ids - {g.id for g in bot.guilds}
    if missing:
        logger.error(
            "Bot is NOT in the following guilds: %s  –  invite it first, then restart.",
            ", ".join(str(gid) for gid in missing),
        )
        return

    # Start immediately if the user is already in the source channel
    if await _user_in_source_channel():
        logger.info("Monitored user is already in source channel.  Starting bridge …")
        try:
            await bridge.start()
        except Exception as exc:
            logger.exception("Failed to start bridge on ready: %s", exc)
    else:
        logger.info("Monitored user is NOT in source channel.  Waiting for them to join …")
        asyncio.ensure_future(bridge._idle_watchdog())


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.id != config.SOURCE_USER_ID:
        return

    in_source_now = after.channel is not None and after.channel.id == config.SOURCE_CHANNEL_ID
    was_in_source = before.channel is not None and before.channel.id == config.SOURCE_CHANNEL_ID

    if in_source_now and not bridge.is_running:
        logger.info("Monitored user joined source channel.  Starting bridge …")
        try:
            await bridge.start()
        except Exception as exc:
            logger.exception("Failed to start bridge: %s", exc)

    elif was_in_source and not in_source_now and bridge.is_running:
        logger.info("Monitored user left source channel.  Stopping bridge …")
        await bridge.stop()
        logger.info("Bridge stopped.  Waiting for user to rejoin …")
        asyncio.ensure_future(bridge._idle_watchdog())

# ─────────────────────────────────────────────────────────────────────────────
#  Run
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        bot.run(config.BOT_TOKEN)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    except discord.LoginFailure:
        logger.critical("Invalid bot token!  Check BOT_TOKEN in your .env file.")
        sys.exit(1)
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)
        sys.exit(1)
