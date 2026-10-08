import re
from datetime import time

import pytest

from tgforecast import config

GOOD = {"TELEGRAM_BOT_TOKEN": "123:abc", "CHAT_ID": "-1001"}


def test_defaults():
    s = config.load(GOOD)
    assert (s.city, s.post_at, str(s.tz), s.units, str(s.data_dir)) == (
        "Vienna",
        time(7, 0),
        "Europe/Vienna",
        "metric",
        "data",
    )


def test_overrides():
    s = config.load(
        {
            **GOOD,
            "CITY": "Graz",
            "POST_AT": "06:45",
            "TZ": "UTC",
            "UNITS": "imperial",
            "DATA_DIR": "/data",
        }
    )
    assert (s.city, s.post_at, str(s.tz), s.units, str(s.data_dir)) == (
        "Graz",
        time(6, 45),
        "UTC",
        "imperial",
        "/data",
    )


@pytest.mark.parametrize(
    "env, says",
    [
        ({}, "TELEGRAM_BOT_TOKEN"),
        ({"TELEGRAM_BOT_TOKEN": "123:abc"}, "CHAT_ID"),
        ({**GOOD, "POST_AT": "7am"}, "POST_AT"),
        ({**GOOD, "TZ": "Mars/Olympus"}, "TZ"),
        ({**GOOD, "UNITS": "kelvin"}, "UNITS"),
    ],
)
def test_bad_settings_stop_with_the_fix(env, says):
    with pytest.raises(SystemExit) as e:
        config.load(env)
    assert says in str(e.value)


def test_chat_id_not_needed_for_chat_id_lookup():
    assert config.load({"TELEGRAM_BOT_TOKEN": "123:abc"}, need_chat=False).chat_id == ""


def test_token_never_in_the_repr():
    assert "123:abc" not in repr(config.load(GOOD))


ANSWER = {
    "ANSWER_BOT_TOKEN": "456:def",
    "RENDER_EXTERNAL_URL": "https://answer.onrender.com/",
    "WEBHOOK_SECRET": "a+b/c=",
}


def test_answer_settings_for_render():
    s = config.load_answer(ANSWER)
    assert (s.token, s.webhook_url, s.port) == ("456:def", "https://answer.onrender.com", 10000)
    assert re.fullmatch(r"[0-9a-f]{64}", s.secret)  # Telegram allows only A-Z a-z 0-9 _ -
    assert "456:def" not in repr(s) and s.secret not in repr(s)


def test_answer_settings_for_local_polling():
    s = config.load_answer({"ANSWER_BOT_TOKEN": "456:def", "PORT": "8080"})
    assert (s.webhook_url, s.secret, s.port) == ("", "", 8080)


@pytest.mark.parametrize(
    "env, says",
    [
        ({}, "ANSWER_BOT_TOKEN"),
        ({**ANSWER, "RENDER_EXTERNAL_URL": "http://answer.onrender.com"}, "https://"),
        ({**ANSWER, "RENDER_EXTERNAL_URL": "https://"}, "has no host"),
        ({**ANSWER, "WEBHOOK_SECRET": " "}, "WEBHOOK_SECRET"),
        ({**ANSWER, "PORT": "eighty"}, "PORT"),
        ({**ANSWER, "PORT": "70000"}, "PORT"),
    ],
)
def test_bad_answer_settings_stop_with_the_fix(env, says):
    with pytest.raises(SystemExit) as e:
        config.load_answer(env)
    assert says in str(e.value)


def test_stage1_token_is_not_the_answer_token():
    with pytest.raises(SystemExit):
        config.load_answer({"TELEGRAM_BOT_TOKEN": "123:abc"})
