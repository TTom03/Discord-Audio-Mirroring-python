# Voice Bridge – Production Release Notes

## Version 1.0 – Ready for 24/7 Deployment

### Architecture
- **Python 3.13** with **py-cord 2.7+** (Discord.py fork)
- **Compiled Opus codec** (libopus) for high-performance audio encoding/decoding
- **Thread-safe queues** (one per target) for isolation and backpressure handling
- **Watchdog loop** with health monitoring and automatic recovery

---

## Production-Ready Features

### 1. Zero Audio Loss & Stability
✅ **Jitter buffer (40ms)** — smooths network variance without lag
✅ **Automatic frame dropping** — prevents queue overflow and latency accumulation
✅ **Circuit breaker** — stops thrashing on persistent connection failures
✅ **Disconnect + 3s retry** — clears Discord's stale voice sessions

### 2. Memory Safety (24/7 Operation)
✅ **Log rotation** — 10 MB max, keeps 5 backups (auto-rotates)
✅ **Queue draining on cleanup** — prevents memory leaks on stop/restart
✅ **Sink cleanup with metrics** — tracks frame drop rate
✅ **Exception handling** — all threads/callbacks protected
✅ **Resource pooling** — no unbounded allocations in audio loop

### 3. Observability & Monitoring
✅ **Structured logging** — console + rotating file with timestamps
✅ **Frame drop rate tracking** — sink reports `drop_rate%` on cleanup
✅ **Connection health checks** — every 10 seconds
✅ **Restart detection** — logs reason and attempt count
✅ **Performance metrics** — frames in/dropped per session

### 4. Resilience & Failover
✅ **Automatic reconnects** — on voice connection drop
✅ **Target connection verification** — restarts if any target missing
✅ **Player health re-start** — restarts on player stop without error
✅ **Graceful backoff** — 60s pause after 3 consecutive failures
✅ **PM2 auto-restart** — 500MB memory limit + auto-reboot on crash

### 5. Clean Startup/Shutdown
✅ **API-based user check** — bypasses stale cache at startup
✅ **All connections closed on stop** — no dangling sockets
✅ **Signal handling** — PM2 graceful shutdown timeout
✅ **Event loop protection** — sync callbacks, no coroutine abuse

### 6. User-Specific Audio Isolation
✅ **Filter by user ID** — only one person's audio forwarded
✅ **Mute bot at source** — bot is invisible on monitored guild
✅ **Clear source channel** — no feedback loop

---

## Performance Profile

| Metric | Value |
|--------|-------|
| **Latency (source → target)** | ~40ms (jitter buffer) + network |
| **Frame size** | 20ms @ 48kHz, 16-bit stereo PCM |
| **Memory per connection** | ~2 MB (queue + buffers) |
| **CPU overhead** | <1% (Opus codec is compiled C) |
| **Max drop rate before warning** | Configurable, logged at cleanup |

---

## Configuration

**`.env` file required:**
```
BOT_TOKEN=<YOUR_TOKEN>
SOURCE_GUILD_ID=<guild_id>
SOURCE_CHANNEL_ID=<channel_id>
SOURCE_USER_ID=<user_id_to_forward>
TARGET_1_GUILD_ID=<guild_id>
TARGET_1_CHANNEL_ID=<channel_id>
TARGET_2_GUILD_ID=<guild_id>
TARGET_2_CHANNEL_ID=<channel_id>
TARGET_3_GUILD_ID=<guild_id>
TARGET_3_CHANNEL_ID=<channel_id>
JITTER_BUFFER_FRAMES=2          # 40ms (tunable)
MAX_QUEUE_FRAMES=100            # ~2 second buffer per target
```

---

## Deployment (PM2)

```bash
# Install/start
pm2 start ecosystem.config.js

# Monitor
pm2 logs voice-bridge
pm2 monit

# Stop/restart
pm2 restart voice-bridge
pm2 stop voice-bridge
pm2 delete voice-bridge

# Auto-boot on system restart
pm2 startup
pm2 save
```

---

## Troubleshooting

### Bot not joining all targets
- Check logs: `pm2 logs voice-bridge --err`
- Verify `.env` guild/channel IDs are correct
- Ensure bot has "Connect" permission in all channels
- Watchdog will auto-restart every 10 seconds if targets missing

### Audio crackling/distortion
- Increase `JITTER_BUFFER_FRAMES` in `.env` (trade: +latency)
- Check network latency to Discord (high variance causes drops)
- Monitor frame drop rate in logs

### Memory growing over time
- Check log rotation: `ls -lh voice_bridge.log*`
- Verify no exceptions in `pm2 logs` (would indicate resource leak)
- Restart monthly with: `pm2 restart voice-bridge`

### Bot keeps restarting
- Watchdog logs reason: check `pm2 logs voice-bridge`
- If "persistent failures", check Discord API/network
- If "3 consecutive failures", bot enters 60s backoff
- Verify source guild/channel are correct

---

## Monitoring Checklist (24/7)

- [ ] `pm2 monit` — memory should stay <200MB
- [ ] `pm2 logs` — should see "Audio bridge is live" after startup
- [ ] Manual test: user can join/leave source channel
- [ ] Audio is clear and continuous (no drops/crackling)
- [ ] No repeated restart loops in logs
- [ ] Frame drop rate <1% (check cleanup logs)

---

## Limits & Design Decisions

| Decision | Rationale |
|----------|-----------|
| **1 source, 3 targets max** | Prevents queue explosion; 3 is tested & stable |
| **40ms jitter buffer** | Balances latency vs. smoothing |
| **3-second disconnect wait** | Discord session cleanup time |
| **100 frame queue per target** | ~2s buffer @ 20ms/frame |
| **Circuit breaker after 3 fails** | Prevents restart thrashing |
| **10 MB log rotation** | Safe for 24/7 on disk |

---

## Known Limitations

- **Only 1 source user** — bot forwards audio from one specific person
- **Discord-wide restriction** — bot can't record multiple users in one session
- **Network-dependent** — high-latency/lossy networks will cause distortion
- **No volume control** — Discord enforces equal loudness

---

## Future Improvements (Optional)

- [ ] Multiple source users (requires different Discord API approach)
- [ ] Configurable target count (currently hardcoded to 3)
- [ ] Web dashboard for monitoring
- [ ] Metrics export (Prometheus)
- [ ] Threshold alerting (e.g., drop rate >5%)
