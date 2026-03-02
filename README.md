# Voice Bridge

A Discord bot that forwards one user's voice to multiple channels at the same time. Runs 24/7 with auto-reconnect and handles network issues gracefully.

## Introduction

Voice Bridge monitors a specific Discord user and broadcasts their audio to multiple target channels across different servers. Once configured, it runs automatically—starts forwarding audio when the user joins, stops when they leave. Built for reliability with proper error handling, memory management, and logging.

## Features

- Monitor one Discord user and broadcast their voice to multiple channels
- Automatic start/stop based on user presence
- Handles network issues with jitter buffering and auto-reconnect
- Log rotation to prevent disk bloat
- Thread-safe audio queues for each target
- Health checks and metrics logging
- Works with PM2 or systemd

## Prerequisites
- Python 3.13+
- A Discord bot token (with voice permissions)
- The servers and channels you want to use

## Installation Instructions

1. Clone the repo:
   ```bash
   git clone https://github.com/yourusername/voice-bridge.git
   cd voice-bridge
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with your settings:
   ```env
   BOT_TOKEN=your_bot_token_here
   
   # Source (the user to monitor and where to listen)
   SOURCE_USER_ID=user_id_to_monitor
   SOURCE_GUILD_ID=server_id_with_source_channel
   SOURCE_CHANNEL_ID=voice_channel_id_to_listen_to
   
   # Targets (up to 3 target channels to forward audio to)
   TARGET_1_GUILD_ID=target_server_1
   TARGET_1_CHANNEL_ID=target_voice_channel_1
   
   TARGET_2_GUILD_ID=target_server_2
   TARGET_2_CHANNEL_ID=target_voice_channel_2
   
   TARGET_3_GUILD_ID=target_server_3
   TARGET_3_CHANNEL_ID=target_voice_channel_3
   
   # Optional: fine-tune audio settings
   JITTER_BUFFER_FRAMES=2
   MAX_QUEUE_FRAMES=100
   ```

4. Run it:
   ```bash
   python bot.py
   ```

## Configuration

All settings are in `.env`. The main variables are:

**Required:**
- `BOT_TOKEN` — Your Discord bot token
- `SOURCE_USER_ID` — The Discord user ID to monitor
- `SOURCE_GUILD_ID` — The server where the source channel is
- `SOURCE_CHANNEL_ID` — The voice channel to listen to
- `TARGET_*_GUILD_ID` and `TARGET_*_CHANNEL_ID` — Up to 3 target servers/channels

**Optional:**
- `JITTER_BUFFER_FRAMES` — How many frames to buffer (default: 2)
- `MAX_QUEUE_FRAMES` — Max queue depth per target (default: 100)

## How It Works

The bot listens for audio from one user, captures it as PCM data, queues it for each target channel, and plays it back. Each target gets its own queue so if one channel lags, it doesn't affect the others.

```
Discord (Opus) → Decode → PCM → Queue per target → Re-encode → Send to targets
```

## Running It
