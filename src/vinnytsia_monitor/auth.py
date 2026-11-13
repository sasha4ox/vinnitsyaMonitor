"""Interactive local login. The running worker never prompts."""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys
import tempfile
from pathlib import Path

from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from vinnytsia_monitor.client_factory import build_client
from vinnytsia_monitor.errors import ConfigError, SessionMissingError, SettingsError
from vinnytsia_monitor.logging_config import configure_logging
from vinnytsia_monitor.session_store import read_existing_session, save_session
from vinnytsia_monitor.settings import load_settings

logger = logging.getLogger("vinnytsia_monitor.auth")


def code_delivery_message(sent_type: object) -> tuple[bool, str]:
    """Explain where Telegram put the login code.

    The first value is whether a code was actually sent. Official-app login
    and this API login do not use the same delivery channel.
    """
    name = type(sent_type).__name__
    if name == "SentCodeTypeApp":
        return True, (
            "Telegram sent the code inside the Telegram app, not by SMS. "
            "Open the service chat named Telegram. The message is from Telegram itself."
        )
    if name == "SentCodeTypeSms":
        return True, "Telegram sent the code by SMS."
    if name == "SentCodeTypeCall":
        return True, "Telegram is calling this number. The code is spoken in the call."
    if name == "SentCodeTypeFlashCall":
        return True, "Telegram is placing a flash call. The code is in the caller number."
    if name == "SentCodeTypeMissedCall":
        return True, "Telegram is placing a missed call. The code is the last digits of the caller number."
    if name == "SentCodeTypeEmailCode":
        pattern = getattr(sent_type, "email_pattern", None) or "the login email"
        return True, f"Telegram sent the code to {pattern}, not into the Telegram app."
    if name == "SentCodeTypeSetUpEmailRequired":
        return False, (
            "Telegram did not send a code. An API login on this account requires a login email first. "
            "In the official Telegram app open Settings, Privacy and Security, add a login email, then run this command again."
        )
    if name in {"SentCodeTypeFirebaseSms", "SentCodeTypeFragmentSms", "SentCodeTypeSmsWord", "SentCodeTypeSmsPhrase"}:
        return False, (
            "Telegram accepted the number but will not deliver a normal code to this app. "
            "In the official Telegram app open Settings, Privacy and Security, add a login email, then run this command again."
        )
    return True, f"Telegram answered with {name}. Enter the code if you received one."


def main() -> None:
    if not sys.stdin.isatty():
        print("Interactive authentication needs a terminal.", file=sys.stderr)
        raise SystemExit(1)
    try:
        asyncio.run(_auth())
    except (SettingsError, ConfigError, SessionMissingError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        raise SystemExit(130) from None


async def _auth() -> None:
    settings = load_settings()
    existing = read_existing_session(settings.session_path, settings.session_string)
    configure_logging(
        settings.log_level,
        settings.log_format,
        settings.redaction_secrets() + ([existing] if existing else []),
    )
    client = build_client(settings.api_id, settings.api_hash, existing)
    await client.connect()
    try:
        await _ensure_login(client)
        saved = client.session.save()
        save_session(settings.session_path, saved)
        me = await client.get_me()
        account = f"@{me.username}" if me is not None and me.username else "the authorized account"
        logger.info("Authorized as %s", account)
        logger.info("Saved the Telegram session to %s", settings.session_path)
        logger.info("This file is a secret. Do not commit it or paste it into logs.")
    finally:
        await client.disconnect()


def write_login_qr(url: str, path: Path) -> None:
    import segno

    segno.make(url, error="m").save(path, scale=8)


def open_login_qr(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
        return
    import subprocess

    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.run([opener, str(path)], check=False)


async def _ensure_login(client) -> None:
    if await client.is_user_authorized():
        return

    print(
        "Telegram often never shows the login code in the app, even after it says the code was sent there.\n"
        "Use the phone where this account is already open.\n"
        "Settings → Devices → Link Desktop Device, then scan the QR image.\n"
        "Leave this window open until it says the account is authorized.\n"
        "Press Enter to open the QR image, or type phone to try a login code instead."
    )
    choice = input().strip().casefold()
    if choice == "phone":
        await _login_with_code(client)
        return
    await _login_with_qr(client)


async def _login_with_qr(client) -> None:
    image = Path(tempfile.gettempdir()) / "vinnytsia-telegram-login-qr.svg"
    try:
        for attempt in range(3):
            qr_login = await client.qr_login()
            write_login_qr(qr_login.url, image)
            open_login_qr(image)
            print("QR image opened. Scan it from the phone. Waiting...")
            try:
                await qr_login.wait()
                return
            except TimeoutError:
                if attempt == 2:
                    print("The QR code expired before it was scanned.", file=sys.stderr)
                    raise SystemExit(1)
                print("That QR code expired. Opening a new one.")
            except SessionPasswordNeededError:
                password = getpass.getpass("Two-factor password: ")
                await client.sign_in(password=password)
                return
    finally:
        try:
            image.unlink(missing_ok=True)
        except OSError:
            pass


async def _login_with_code(client) -> None:
    phone = input("Phone number, in international format: ").strip()
    try:
        sent = await client.send_code_request(phone)
    except FloodWaitError as exc:
        print(f"Telegram is refusing another code for {exc.seconds} seconds. Wait, then try again.", file=sys.stderr)
        raise SystemExit(1) from exc
    except PhoneNumberFloodError as exc:
        print("Telegram temporarily stopped sending codes to this number. Wait and try again later.", file=sys.stderr)
        raise SystemExit(1) from exc
    except PhoneNumberInvalidError as exc:
        print("Telegram rejected that phone number. Use the international form, for example +380...", file=sys.stderr)
        raise SystemExit(1) from exc
    except PhoneNumberBannedError as exc:
        print("Telegram will not send a login code to this number.", file=sys.stderr)
        raise SystemExit(1) from exc
    except ApiIdInvalidError as exc:
        print("API_ID or API_HASH was rejected. Check the values from https://my.telegram.org.", file=sys.stderr)
        raise SystemExit(1) from exc

    ask, message = code_delivery_message(sent.type)
    print(message)
    if not ask:
        raise SystemExit(1)

    for _ in range(3):
        code = input("Code: ").strip()
        try:
            await client.sign_in(phone, code)
            return
        except PhoneCodeInvalidError:
            print("That code was not accepted. Try the same code again, or request a new login.", file=sys.stderr)
        except SessionPasswordNeededError:
            password = getpass.getpass("Two-factor password: ")
            await client.sign_in(password=password)
            return
    print("Could not sign in after 3 attempts.", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
