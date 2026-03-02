"""
audio_bridge.py – Core audio-routing logic.

Data flow (per 20 ms Discord voice tick):
  Discord (Opus) → py-cord decode → PCM bytes
        → UserAudioSink.write()
        → thread-safe Queue  (one per target)
        → QueueAudioSource.read()
        → discord.VoiceClient (re-encode Opus) → target server
"""

from __future__ import annotations

import asyncio
import logging
import queue

import discord
from discord.sinks import Sink

logger = logging.getLogger("voice_bridge.audio")

# 20 ms of 48 kHz stereo 16-bit PCM  (48000 * 2 channels * 2 bytes * 0.02 s)
FRAME_SIZE: int = 3840
_SILENCE: bytes = bytes(FRAME_SIZE)


# ─────────────────────────────────────────────────────────────────────────────
#  Sink: capture PCM from one specific user
# ─────────────────────────────────────────────────────────────────────────────

class UserAudioSink(Sink):
    """
    Receives decoded PCM frames from py-cord's voice stack and fans them out
    to one thread-safe Queue per target voice connection.

    Frames from *every* user arrive here; we drop everything that does not
    come from source_user_id so targets only hear one person.
    """

    def __init__(
        self,
        source_user_id: int,
        audio_queues: list[queue.Queue],
        max_queue_frames: int = 100,
    ) -> None:
        super().__init__()
        self.source_user_id  = source_user_id
        self.audio_queues    = audio_queues
        self.max_queue_frames = max_queue_frames
        self._active         = True
        self._frames_in      = 0
        self._frames_dropped = 0

    # py-cord calls write(data, user) from its internal audio thread.
    # `data` is raw PCM bytes; `user` is a Member or int (SSRC-mapped user id).
    def write(self, data: bytes, user) -> None:
        if not self._active:
            return
        try:
            user_id = user.id if hasattr(user, "id") else int(user)
            if user_id != self.source_user_id:
                return

            self._frames_in += 1
            frame = data if len(data) == FRAME_SIZE else (data + _SILENCE)[:FRAME_SIZE]

            for q in self.audio_queues:
                # Trim the oldest frame(s) if the target is falling behind,
                # so latency can never grow unboundedly.
                try:
                    while q.qsize() >= self.max_queue_frames:
                        try:
                            q.get_nowait()
                            self._frames_dropped += 1
                        except queue.Empty:
                            break
                except Exception as exc:
                    logger.debug("Error checking queue size: %s", exc)
                    continue

                try:
                    q.put_nowait(frame)
                except queue.Full:
                    self._frames_dropped += 1
                except Exception as exc:
                    logger.warning("Error putting frame in queue: %s", exc)
        except Exception as exc:
            logger.warning("Error in sink.write(): %s", exc)

    def cleanup(self) -> None:
        self._active = False
        # Drain remaining frames from queues to free memory
        for q in self.audio_queues:
            try:
                while not q.empty():
                    q.get_nowait()
            except Exception:
                pass
        
        frame_drop_rate = (
            100.0 * self._frames_dropped / (self._frames_in + self._frames_dropped)
            if (self._frames_in + self._frames_dropped) > 0
            else 0.0
        )
        logger.info(
            "Sink cleaned up. frames_in=%d frames_dropped=%d drop_rate=%.2f%%",
            self._frames_in,
            self._frames_dropped,
            frame_drop_rate,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Source: feed PCM to a target voice connection
# ─────────────────────────────────────────────────────────────────────────────

class QueueAudioSource(discord.AudioSource):
    """
    AudioSource backed by a thread-safe Queue of 20 ms PCM frames.

    A small *jitter buffer* accumulates a few frames before playback begins
    (and after every gap) so that minor network jitter does not cause pops or
    stuttering.  The buffer is kept deliberately small (default 2 frames =
    40 ms) to minimise end-to-end latency.
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        jitter_buffer_frames: int = 2,
    ) -> None:
        self.queue               = audio_queue
        self.jitter_buffer_frames = max(1, jitter_buffer_frames)
        self._buffering          = True
        self._consecutive_silence = 0
        self._frames_played      = 0

    # Called every 20 ms by discord's internal player thread.
    def read(self) -> bytes:
        # ── Jitter-buffer fill phase ──────────────────────────────────────
        if self._buffering:
            if self.queue.qsize() >= self.jitter_buffer_frames:
                self._buffering = False
                logger.debug("Jitter buffer filled – starting playback")
            else:
                return _SILENCE

        # ── Normal playback ───────────────────────────────────────────────
        try:
            frame = self.queue.get_nowait()
            self._consecutive_silence = 0
            self._frames_played += 1
            return frame
        except queue.Empty:
            self._consecutive_silence += 1
            # After ~80 ms of silence re-enter buffering so next burst
            # starts cleanly instead of playing one frame then going silent.
            # (Faster re-buffering = faster recovery from gaps)
            if self._consecutive_silence > 4:
                self._buffering = True
                self._consecutive_silence = 0
                logger.debug("Gap detected – re-entering jitter buffer")
            return _SILENCE

    def is_opus(self) -> bool:
        # Returning False tells py-cord to Opus-encode our PCM frames.
        return False

    def cleanup(self) -> None:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Bridge orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class AudioBridge:
    """
    Manages the lifecycle of one source voice connection (recording) and N
    target voice connections (playback).

    Usage::

        bridge = AudioBridge(bot, ...)
        await bridge.start()   # connect & begin streaming
        await bridge.stop()    # disconnect everything cleanly
    """

    def __init__(
        self,
        bot: discord.Bot,
        source_guild_id: int,
        source_channel_id: int,
        source_user_id: int,
        targets: list[dict],          # [{"guild_id": int, "channel_id": int}, ...]
        jitter_buffer_frames: int = 2,
        max_queue_frames: int = 100,
    ) -> None:
        self.bot                  = bot
        self.source_guild_id      = source_guild_id
        self.source_channel_id    = source_channel_id
        self.source_user_id       = source_user_id
        self.targets              = targets
        self.jitter_buffer_frames = jitter_buffer_frames
        self.max_queue_frames     = max_queue_frames

        self._running: bool                          = False
        self._source_vc: discord.VoiceClient | None  = None
        self._target_vcs: list[discord.VoiceClient]  = []
        self._audio_queues: list[queue.Queue]         = []
        self._sources: list[QueueAudioSource]         = []
        self._sink: UserAudioSink | None              = None
        self._watchdog_task: asyncio.Task | None      = None

    # ── Public API ────────────────────────────────────────────────────────

    async def _safe_connect(self, channel: discord.VoiceChannel, mute: bool = False) -> discord.VoiceClient:
        """
        Connect to a voice channel.
        Disconnect any existing local session first.
        py-cord's retry loop handles 4006 errors automatically.
        If mute=True, mute the bot's microphone after connecting.
        """
        guild = channel.guild

        if guild.voice_client is not None:
            logger.info("Disconnecting existing session in '%s' …", guild.name)
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception:
                pass
            await asyncio.sleep(0.5)

        logger.info("Connecting to '%s' in '%s' …", channel.name, guild.name)
        vc = await channel.connect(timeout=30.0)
        await asyncio.sleep(0.2)  # ensure connection is fully established

        if mute:
            logger.info("Muting bot microphone in '%s' …", guild.name)
            try:
                await guild.change_voice_state(channel=vc.channel, self_mute=True)
            except Exception as exc:
                logger.warning("Failed to mute bot in '%s': %s", guild.name, exc)

        return vc

    async def start(self) -> None:
        if self._running:
            logger.warning("Bridge.start() called but bridge is already running.")
            return

        logger.info("Starting audio bridge …")

        # One queue per target so each connection has its own independent buffer.
        self._audio_queues = [
            queue.Queue(maxsize=self.max_queue_frames)
            for _ in self.targets
        ]

        # ── Connect source ────────────────────────────────────────────────
        source_guild = self.bot.get_guild(self.source_guild_id)
        if not source_guild:
            raise RuntimeError(f"Source guild {self.source_guild_id} not found — is the bot in that server?")

        source_channel = source_guild.get_channel(self.source_channel_id)
        if not source_channel:
            raise RuntimeError(f"Source channel {self.source_channel_id} not found.")

        self._source_vc = await self._safe_connect(source_channel, mute=True)
        logger.info("Connected to source: %s / %s", source_guild.name, source_channel.name)

        # ── Connect targets ───────────────────────────────────────────────
        for idx, target in enumerate(self.targets, start=1):
            tg = self.bot.get_guild(target["guild_id"])
            if not tg:
                logger.error("Target %d: guild %d not found – skipped.", idx, target["guild_id"])
                # Still add a dummy vc slot so queue indices stay aligned
                self._target_vcs.append(None)  # type: ignore[arg-type]
                continue

            tc = tg.get_channel(target["channel_id"])
            if not tc:
                logger.error("Target %d: channel %d not found – skipped.", idx, target["channel_id"])
                self._target_vcs.append(None)  # type: ignore[arg-type]
                continue

            vc = await self._safe_connect(tc)
            self._target_vcs.append(vc)
            logger.info("Connected to target %d: %s / %s", idx, tg.name, tc.name)

        # ── Start playback on every live target ───────────────────────────
        for i, vc in enumerate(self._target_vcs):
            if vc is None:
                self._sources.append(None)  # type: ignore[arg-type]
                continue
            src = QueueAudioSource(self._audio_queues[i], self.jitter_buffer_frames)
            self._sources.append(src)
            vc.play(src, after=lambda err, idx=i: self._on_player_error(err, idx))

        # ── Start recording on source ─────────────────────────────────────
        self._sink = UserAudioSink(
            self.source_user_id,
            self._audio_queues,
            self.max_queue_frames,
        )
        self._source_vc.start_recording(self._sink, self._on_recording_finished)

        self._running = True
        self._watchdog_task = asyncio.ensure_future(self._watchdog())
        logger.info(
            "Audio bridge is live! Forwarding user %d → %d target(s).",
            self.source_user_id,
            sum(1 for v in self._target_vcs if v is not None),
        )

    async def stop(self) -> None:
        if not self._running:
            return

        logger.info("Stopping audio bridge …")
        self._running = False

        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None

        if self._source_vc and self._source_vc.is_connected():
            try:
                self._source_vc.stop_recording()
            except Exception:
                pass
            await self._source_vc.disconnect(force=True)
        self._source_vc = None

        # Explicitly clean up the sink
        if self._sink is not None:
            try:
                self._sink.cleanup()
            except Exception:
                pass
            self._sink = None

        for vc in self._target_vcs:
            if vc and vc.is_connected():
                vc.stop()
                await vc.disconnect(force=True)

        self._target_vcs.clear()
        self._audio_queues.clear()
        self._sources.clear()
        logger.info("Audio bridge stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal helpers ──────────────────────────────────────────────────

    def _on_player_error(self, error: Exception | None, target_index: int) -> None:
        if error:
            logger.error("Player error on target %d: %s", target_index, error)

    async def _on_recording_finished(self, sink: UserAudioSink) -> None:
        """Called by py-cord when stop_recording() is invoked (must be async)."""
        logger.info(
            "Recording ended. frames_in=%d frames_dropped=%d",
            sink._frames_in,
            sink._frames_dropped,
        )

    async def _idle_watchdog(self) -> None:
        """
        Polls while the bridge is NOT running.
        Handles the case where a Discord gateway reconnect caused us to miss
        the on_voice_state_update event for the monitored user joining.
        """
        CHECK_INTERVAL = 15  # seconds
        while not self._running:
            await asyncio.sleep(CHECK_INTERVAL)
            if self._running:
                return
            try:
                guild = self.bot.get_guild(self.source_guild_id)
                if guild is None:
                    continue
                member = await guild.fetch_member(self.source_user_id)
                if (
                    member.voice is not None
                    and member.voice.channel is not None
                    and member.voice.channel.id == self.source_channel_id
                ):
                    logger.info(
                        "Idle watchdog: user %d found in source channel — starting bridge …",
                        self.source_user_id,
                    )
                    await self.start()
                    return
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("Idle watchdog check failed: %s", exc)

    async def _watchdog(self) -> None:
        """
        Periodically checks that every voice connection is still alive and
        restarts the bridge automatically if any connection drops or failed.
        Includes circuit breaker to prevent restart thrashing.
        """
        CHECK_INTERVAL = 10  # seconds
        max_consecutive_failures = 3
        consecutive_failures = 0
        watchdog_iteration = 0

        while self._running:
            await asyncio.sleep(CHECK_INTERVAL)
            watchdog_iteration += 1
            try:
                need_restart = False
                reason = None

                # Check source connection
                if self._source_vc is None:
                    reason = "source VC is None"
                    need_restart = True
                elif not self._source_vc.is_connected():
                    reason = "source VC disconnected"
                    need_restart = True

                # Every 5th iteration (~50s), verify user is still in source channel
                # This is a safety net in case voice_state_update events are missed
                if not need_restart and watchdog_iteration % 5 == 0:
                    try:
                        guild = self.bot.get_guild(self.source_guild_id)
                        if guild:
                            member = await guild.fetch_member(self.source_user_id)
                            if member.voice is None or member.voice.channel.id != self.source_channel_id:
                                reason = "monitored user left source channel (watchdog detected)"
                                need_restart = True
                    except Exception as exc:
                        logger.debug("Watchdog user presence check failed: %s", exc)

                # Check that all target connections exist and are connected
                if not need_restart:
                    expected_target_count = len(self.targets)
                    connected_targets = sum(
                        1 for vc in self._target_vcs
                        if vc is not None and vc.is_connected()
                    )
                    if connected_targets < expected_target_count:
                        reason = f"only {connected_targets}/{expected_target_count} targets connected"
                        need_restart = True

                # Check that no target is None (failed connection)
                if not need_restart:
                    for i, vc in enumerate(self._target_vcs):
                        if vc is None:
                            reason = f"target {i+1} is None (failed to connect)"
                            need_restart = True
                            break

                # Check player status on each target
                if not need_restart:
                    for i, vc in enumerate(self._target_vcs):
                        if vc and not vc.is_playing() and not vc.is_paused():
                            logger.warning("Watchdog: target %d player stopped. Restarting …", i + 1)
                            src = QueueAudioSource(
                                self._audio_queues[i], self.jitter_buffer_frames
                            )
                            self._sources[i] = src
                            vc.play(src, after=lambda err, idx=i: self._on_player_error(err, idx))

                if need_restart:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        logger.error(
                            "Watchdog: %d consecutive failures (%s). Backing off for 60s …",
                            consecutive_failures, reason,
                        )
                        await asyncio.sleep(60)
                        consecutive_failures = 0
                        continue

                    logger.warning("Watchdog: restart needed (%s). Attempt %d/%d …",
                                   reason, consecutive_failures, max_consecutive_failures)
                    await self.stop()
                    await asyncio.sleep(3)
                    try:
                        await self.start()
                        consecutive_failures = 0
                    except Exception as exc:
                        logger.exception("Failed to restart bridge: %s", exc)
                else:
                    consecutive_failures = 0

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.exception("Watchdog error: %s", exc)
