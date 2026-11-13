from vinnytsia_monitor.auth import code_delivery_message, write_login_qr


def test_app_code_tells_the_user_to_open_telegram():
    sent = type("SentCodeTypeApp", (), {"length": 5})()

    ask, message = code_delivery_message(sent)

    assert ask is True
    assert "Telegram app" in message


def test_missing_login_email_does_not_ask_for_a_code():
    sent = type("SentCodeTypeSetUpEmailRequired", (), {})()

    ask, message = code_delivery_message(sent)

    assert ask is False
    assert "did not send a code" in message


def test_login_qr_file_contains_the_telegram_url(tmp_path):
    url = "tg://login?token=abc"
    image = tmp_path / "telegram-login-qr.svg"

    write_login_qr(url, image)

    contents = image.read_text(encoding="utf-8")
    assert contents.startswith("<?xml")
    assert "<svg" in contents


def test_email_code_names_the_masked_address():
    sent = type("SentCodeTypeEmailCode", (), {"email_pattern": "a***@gmail.com"})()

    ask, message = code_delivery_message(sent)

    assert ask is True
    assert "a***@gmail.com" in message
