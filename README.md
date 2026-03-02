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
   DISCORD_TOKEN=your_bot_token
   MONITORED_USER_ID=the_user_to_forward
   MONITORED_GUILD_ID=the_server_with_source_channel
   SOURCE_CHANNEL_ID=the_voice_channel_to_listen_to
   TARGET_CHANNELS=target_channel_1,target_channel_2
   ```

4. Run it:
   ```bash
   python bot.py
   ```

## Configuration

Edit `config.py` to change:
- Which user to monitor
- Which channels to forward to
- Jitter buffer size (default 40ms works fine)
- Reconnect retry settings
- Log levels

## How It Works

The bot listens for audio from one user, captures it as PCM data, queues it for each target channel, and plays it back. Each target gets its own queue so if one channel lags, it doesn't affect the others.

```
Discord (Opus) → Decode → PCM → Queue per target → Re-encode → Send to targets
```

## Running It
