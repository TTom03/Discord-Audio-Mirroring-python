# Voice Bridge

A Discord bot that forwards one user's voice to multiple channels simultaneously.

## Features

- Monitor one user and broadcast their audio
- Auto start/stop with user presence
- 24/7 with auto-reconnect
- Jitter buffering for smooth audio
- Health monitoring

## Setup

### 1. Clone & Install
```bash
git clone https://github.com/TTom03/Discord-Audio-Mirroring-python.git
cd Discord-Audio-Mirroring-python
pip install -r requirements.txt
```

### 2. Configure `.env`
```env
BOT_TOKEN=your_bot_token

SOURCE_USER_ID=user_to_monitor
SOURCE_GUILD_ID=source_server  
SOURCE_CHANNEL_ID=source_channel

TARGET_1_GUILD_ID=target_server_1
TARGET_1_CHANNEL_ID=target_channel_1

TARGET_2_GUILD_ID=target_server_2
TARGET_2_CHANNEL_ID=target_channel_2

TARGET_3_GUILD_ID=target_server_3
TARGET_3_CHANNEL_ID=target_channel_3
```

### 3. Run

**Development:**
```bash
python bot.py
```

**Production (PM2):**
```bash
npm install -g pm2
pm2 start ecosystem.config.js
pm2 logs voice-bridge
pm2 save
```

## How It Works

Captures audio from one user → Forwards to multiple channels → Plays in real-time.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot won't start | Check `.env` has all required variables |
| No audio | Verify bot has `Connect` + `Speak` permissions |
| High CPU/Memory | Run `pm2 logs voice-bridge` to check |

## Files

- `bot.py` - Main bot
- `audio_bridge.py` - Audio routing  
- `config.py` - Load settings
- `ecosystem.config.js` - PM2 config

## Requirements

- Python 3.13+
- py-cord ≥2.7.0
- PyNaCl, python-dotenv, audioop-lts
- libopus (system library)

See `PRODUCTION.md` for advanced options.

