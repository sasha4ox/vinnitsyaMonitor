import logging

import pytest

from vinnytsia_monitor.channels import parse_channel_ref
from vinnytsia_monitor.dedup import DedupCache
from vinnytsia_monitor.errors import ConfigError, SessionMissingError, SettingsError
from vinnytsia_monitor.flood import flood_wait_delay
from vinnytsia_monitor.logging_config import RedactFilter
from vinnytsia_monitor.notify import TELEGRAM_LIMIT, format_notification
from vinnytsia_monitor.pipeline.normalize import normalize
from vinnytsia_monitor.session_store import resolve_session
from vinnytsia_monitor.settings import parse_bool, settings_from_mapping


def test_normalize_folds_case_width_and_dashes():
    assert normalize("  Він\u200bниця\u00a0—\u00a0ВІННИЦЯ  ") == "вінниця - вінниця"
    assert normalize("Ёлка") == "елка"
    assert normalize("Лука–Мелешківська") == "лука-мелешківська"


def test_channel_references():
    assert parse_channel_ref("https://t.me/vin_info_ppo") == "vin_info_ppo"
    assert parse_channel_ref("https://t.me/vin_info_ppo?single") == "vin_info_ppo"
    assert parse_channel_ref("@Whynotinukrainian") == "Whynotinukrainian"
    assert parse_channel_ref("-1001234567890") == -1001234567890

    with pytest.raises(ConfigError):
        parse_channel_ref("https://t.me/+invitehash")
    with pytest.raises(ConfigError):
        parse_channel_ref("abc")


def test_dedup_forgets_the_oldest_key():
    cache = DedupCache(2)

    assert cache.is_duplicate((1, 1)) is False
    assert cache.is_duplicate((1, 1)) is True
    assert cache.is_duplicate((1, 2)) is False
    assert cache.is_duplicate((1, 3)) is False
    assert cache.is_duplicate((1, 1)) is False


def test_flood_wait_above_the_limit_is_skipped():
    assert flood_wait_delay(10, 300) == 10
    assert flood_wait_delay(300, 300) == 300
    assert flood_wait_delay(301, 300) is None
    assert flood_wait_delay(-1, 300) is None


def test_notification_stays_within_the_telegram_limit():
    body = format_notification("а" * 5000, "@vin_info_ppo")

    assert len(body) <= TELEGRAM_LIMIT
    assert body.endswith("Джерело: @vin_info_ppo")
    assert "…" in body

    with pytest.raises(ValueError):
        format_notification("  ", "@vin_info_ppo")


def test_session_file_wins_over_the_environment(tmp_path):
    path = tmp_path / "nested" / "telegram.session"
    created = resolve_session(path, "abc def\nxyz12345")

    assert created.source == "environment"
    assert created.value == "abcdefxyz12345"
    assert path.read_text(encoding="utf-8").strip() == "abcdefxyz12345"

    kept = resolve_session(path, "replacement-session-value")
    assert kept.source == "file"
    assert kept.value == "abcdefxyz12345"


def test_missing_session_explains_how_to_create_one(tmp_path):
    with pytest.raises(SessionMissingError, match="vinnytsia_monitor.auth"):
        resolve_session(tmp_path / "telegram.session", "  \n")


def test_session_path_must_be_a_file(tmp_path):
    with pytest.raises(SettingsError, match="not a file"):
        resolve_session(tmp_path, None)


def test_log_filter_removes_session_text():
    secret = "session-secret-value"
    record = logging.LogRecord(
        name="vinnytsia_monitor",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="failed with %s",
        args=(secret,),
        exc_info=None,
    )

    assert RedactFilter([secret]).filter(record) is True
    assert secret not in record.getMessage()
    assert "[redacted]" in record.getMessage()


def test_settings_reject_bad_values(tmp_path):
    with pytest.raises(SettingsError, match="API_ID"):
        settings_from_mapping({}, cwd=tmp_path)

    environ = {
        "API_ID": "10",
        "API_HASH": "hash",
        "TELEGRAM_SESSION_PATH": "secrets/telegram.session",
        "INTERACTIVE_AUTH": "maybe",
    }
    with pytest.raises(SettingsError, match="boolean"):
        settings_from_mapping(environ, cwd=tmp_path)

    assert parse_bool("YES", default=False) is True
    assert parse_bool(None, default=False) is False


def test_settings_accept_a_config_directory(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    environ = {
        "API_ID": "10",
        "API_HASH": "a" * 32,
        "TELEGRAM_SESSION_PATH": str(tmp_path / "telegram.session"),
        "CONFIG_DIR": str(config_dir),
        "LOG_LEVEL": "debug",
        "LOG_FORMAT": "json",
        "LOG_MESSAGE_TEXT": "false",
    }

    settings = settings_from_mapping(environ, cwd=tmp_path)

    assert settings.api_id == 10
    assert settings.config_dir == config_dir
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "json"
    assert settings.log_message_text is False
    assert "a" * 32 not in repr(settings)
