"""Live Telegram worker.

NewMessage delivers updates after the client is connected. This module does
not read channel history and does not call iter_messages, get_messages, or catch_up.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from dataclasses import dataclass

from telethon import events
from telethon.errors import (
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    FloodWaitError,
    RPCError,
    SessionRevokedError,
)
from telethon.utils import get_peer_id

from vinnytsia_monitor.channels import parse_channel_ref
from vinnytsia_monitor.client_factory import build_client
from vinnytsia_monitor.config_load import Application, load_application
from vinnytsia_monitor.dedup import DedupCache
from vinnytsia_monitor.errors import ConfigError
from vinnytsia_monitor.flood import flood_wait_delay
from vinnytsia_monitor.logging_config import configure_logging
from vinnytsia_monitor.notify import format_notification
from vinnytsia_monitor.pipeline.engine import evaluate
from vinnytsia_monitor.pipeline.models import Label
from vinnytsia_monitor.session_store import resolve_session, save_session
from vinnytsia_monitor.settings import Settings, load_settings

logger = logging.getLogger("vinnytsia_monitor")

_DEAD_SESSION = (AuthKeyUnregisteredError, AuthKeyDuplicatedError, SessionRevokedError)


@dataclass(frozen=True)
class ResolvedChannel:
    peer_id: int
    dialog_id: int
    title: str
    username: str | None

    @property
    def label(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.title


async def run_worker() -> None:
    settings = load_settings()
    session = resolve_session(settings.session_path, settings.session_string)
    secrets = settings.redaction_secrets()
    if session.value not in secrets:
        secrets.append(session.value)
    configure_logging(settings.log_level, settings.log_format, secrets)

    logger.info("Session loaded from the %s", "session file" if session.source == "file" else "TELEGRAM_SESSION_STRING")
    if session.source == "file" and settings.session_string:
        logger.info("TELEGRAM_SESSION_STRING is ignored because the session file already exists")

    try:
        application = load_application(settings.config_dir)
    except ConfigError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc

    enabled_rules = [rule.name for rule in application.catalog.rules if rule.enabled]
    logger.info("Loaded %s localities", len(application.catalog.locations))
    logger.info("Enabled keyword rules: %s", ", ".join(enabled_rules))

    client = build_client(settings.api_id, settings.api_hash, session.value)
    stop_event = asyncio.Event()
    _install_signals(stop_event)

    await client.connect()
    watcher = asyncio.create_task(_watch_connection(client, stop_event), name="connection-status")
    try:
        await _ensure_authorized(client, settings)
        sources, destination = await _resolve_channels(client, application)
        _install_handler(client, application, settings, sources, destination)
        logger.info("Listening for new messages")
        await _serve(client, stop_event)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        if client.is_connected():
            await client.disconnect()
        logger.info("Monitor stopped")


def _install_signals(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _stop)
        except (ValueError, OSError):
            logger.debug("SIGTERM handler was not installed")


async def _ensure_authorized(client, settings: Settings) -> None:
    import sys

    if await client.is_user_authorized():
        me = await client.get_me()
        account = f"@{me.username}" if me is not None and me.username else "authorized account"
        logger.info("Telegram session is authorized (%s)", account)
        return

    if settings.interactive_auth and sys.stdin.isatty():
        logger.info("Session is not authorized. Starting interactive login.")
        await client.start()
        save_session(settings.session_path, client.session.save())
        logger.info("Saved a new session to %s", settings.session_path)
        return

    logger.error(
        "Telegram session is not authorized. Run python -m vinnytsia_monitor.auth locally "
        "and update the deployed session. The worker does not prompt."
    )
    raise SystemExit(1)


async def _resolve_channels(client, application: Application):
    dialogs = await _load_dialogs(client)
    by_id: dict[int, object] = {}
    by_username: dict[str, object] = {}
    for dialog in dialogs:
        entity = dialog.entity
        by_id[dialog.id] = dialog
        by_id[get_peer_id(entity)] = dialog
        username = getattr(entity, "username", None)
        if username:
            by_username[username.casefold()] = dialog

    sources: list[ResolvedChannel] = []
    seen: set[int] = set()
    for ref in application.source_channels:
        parsed = parse_channel_ref(ref)
        dialog = by_id.get(parsed) if isinstance(parsed, int) else by_username.get(parsed.casefold())
        if dialog is None:
            logger.error(
                "This account is not subscribed to %s. Join that channel in Telegram and restart.",
                ref,
            )
            raise SystemExit(1)
        source = _resolved_channel(dialog)
        if source.peer_id in seen:
            continue
        seen.add(source.peer_id)
        sources.append(source)
        if source.dialog_id != source.peer_id:
            logger.warning(
                "Dialog id %s differs from peer id %s for %s",
                source.dialog_id,
                source.peer_id,
                source.label,
            )
        logger.info("Monitoring %s (%s)", source.label, source.peer_id)

    destination = await client.get_entity(parse_channel_ref(application.destination_channel))
    destination_id = get_peer_id(destination)
    if destination_id in seen:
        logger.error("The destination channel cannot also be a source channel")
        raise SystemExit(1)
    destination_name = getattr(destination, "title", None) or getattr(destination, "username", None) or destination_id
    logger.info("Publishing to %s (%s)", destination_name, destination_id)
    return sources, destination


def _resolved_channel(dialog) -> ResolvedChannel:
    entity = dialog.entity
    username = getattr(entity, "username", None)
    title = dialog.name or username or str(dialog.id)
    return ResolvedChannel(
        peer_id=get_peer_id(entity),
        dialog_id=dialog.id,
        title=title,
        username=username,
    )


async def _load_dialogs(client):
    dialogs = list(await _get_dialogs(client, archived=False))
    dialogs.extend(await _get_dialogs(client, archived=True))
    return dialogs


async def _get_dialogs(client, archived: bool):
    try:
        return await _get_dialogs_once(client, archived)
    except FloodWaitError as exc:
        if exc.seconds > 3600:
            logger.error("FloodWait of %s seconds while loading chats", exc.seconds)
            raise SystemExit(1) from exc
        logger.warning("FloodWait for %s seconds while loading chats", exc.seconds)
        await asyncio.sleep(exc.seconds)
        return await _get_dialogs_once(client, archived)


async def _get_dialogs_once(client, archived: bool):
    try:
        return await client.get_dialogs(archived=archived)
    except TypeError:
        if archived:
            return []
        return await client.get_dialogs()


def _install_handler(client, application: Application, settings: Settings, sources: list[ResolvedChannel], destination) -> None:
    by_chat: dict[int, ResolvedChannel] = {}
    for source in sources:
        by_chat[source.peer_id] = source
        by_chat[source.dialog_id] = source
    dedup = DedupCache(application.dedup_cache_size)

    async def on_message(event) -> None:
        try:
            await _handle_message(event, application, settings, by_chat, dedup, destination)
        except Exception:
            logger.exception("Failed to process message %s", getattr(event, "id", "?"))

    client.add_event_handler(on_message, events.NewMessage(chats=list(by_chat), incoming=True))


async def _handle_message(event, application: Application, settings: Settings, by_chat, dedup: DedupCache, destination) -> None:
    if dedup.is_duplicate((event.chat_id, event.id)):
        logger.debug("Duplicate update for chat %s message %s", event.chat_id, event.id)
        return

    source = by_chat.get(event.chat_id)
    source_name = source.label if source is not None else str(event.chat_id)
    text = event.raw_text or ""
    if not text.strip():
        logger.info("Skipped message %s in %s: no text", event.id, source_name)
        return

    decision = evaluate(text, application.catalog)
    logger.info(
        "message chat_id=%s message_id=%s label=%s forward=%s locations=%s rules=%s reasons=%s",
        event.chat_id,
        event.id,
        decision.label.value,
        "yes" if decision.should_forward else "no",
        ",".join(decision.location_ids) or "-",
        ",".join(decision.matched_rules) or "-",
        " | ".join(decision.reasons),
    )
    if settings.log_message_text and decision.label is not Label.SENSITIVE_OPERATIONAL_DETAILS:
        preview = " ".join(text.split())[:500]
        logger.info("message text chat_id=%s message_id=%s text=%s", event.chat_id, event.id, preview)
    if not decision.should_forward:
        return

    published = await _publish(
        event.client,
        destination,
        format_notification(text, source_name),
        application.flood_wait_max_seconds,
    )
    if published:
        logger.info("Published message %s from %s", event.id, source_name)


async def _publish(client, destination, text: str, flood_max: int) -> bool:
    retried = False
    while True:
        try:
            await client.send_message(destination, text, link_preview=False, parse_mode=None)
            return True
        except FloodWaitError as exc:
            delay = flood_wait_delay(exc.seconds, flood_max)
            if delay is None or retried:
                logger.warning("Skipping publish after FloodWait of %s seconds", exc.seconds)
                return False
            retried = True
            logger.warning("FloodWait for %s seconds before publish", delay)
            await asyncio.sleep(delay)
        except RPCError:
            logger.exception("Telegram rejected the notification")
            return False


async def _serve(client, stop_event: asyncio.Event) -> None:
    backoff = 2
    while not stop_event.is_set():
        started = time.monotonic()
        try:
            if not client.is_connected():
                await client.connect()
            logger.info("Telegram connection status: connected")
            disconnected = asyncio.create_task(client.run_until_disconnected())
            stopping = asyncio.create_task(stop_event.wait())
            done, pending = await asyncio.wait(
                {disconnected, stopping},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_event.is_set() and client.is_connected():
                await client.disconnect()
            for task in pending:
                task.cancel()
            results = await asyncio.gather(*done, *pending, return_exceptions=True)
            for result in results:
                if isinstance(result, _DEAD_SESSION) or isinstance(result, FloodWaitError):
                    raise result
                if isinstance(result, Exception):
                    logger.warning("Telegram connection ended with %s", result.__class__.__name__)
        except FloodWaitError as exc:
            logger.warning("FloodWait for %s seconds on the connection", exc.seconds)
            await _sleep(min(max(exc.seconds, 0), 3600), stop_event)
            continue
        except _DEAD_SESSION as exc:
            logger.error(
                "Telegram session is no longer valid (%s). Run python -m vinnytsia_monitor.auth and replace the deployed session.",
                exc.__class__.__name__,
            )
            raise SystemExit(1) from exc
        except (OSError, ConnectionError, RPCError) as exc:
            logger.warning(
                "Telegram connection error (%s); reconnecting in %s seconds",
                exc.__class__.__name__,
                backoff,
            )
            await _sleep(backoff, stop_event)
            backoff = min(backoff * 2, 60)
            continue

        if stop_event.is_set():
            logger.info("Shutdown requested")
            return

        elapsed = time.monotonic() - started
        if elapsed >= 30:
            backoff = 2
        logger.warning("Telegram connection dropped; reconnecting in %s seconds", backoff)
        await _sleep(backoff, stop_event)
        if elapsed < 30:
            backoff = min(backoff * 2, 60)


async def _watch_connection(client, stop_event: asyncio.Event) -> None:
    previous: bool | None = None
    while not stop_event.is_set():
        connected = client.is_connected()
        if connected != previous:
            logger.info("Telegram connection status: %s", "connected" if connected else "disconnected")
            previous = connected
        await _sleep(15, stop_event)


async def _sleep(seconds: float, stop_event: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return
