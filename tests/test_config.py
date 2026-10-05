from datetime import time

import pytest

from tgforecast import config

GOOD = {"TELEGRAM_BOT_TOKEN": "123:abc", "CHAT_ID": "-1001"}


def test_defaults():
    s = config.load(GOOD)
    assert (s.city, s.post_at, str(s.tz), s.units, str(s.data_dir)) == \
        ("Vienna", time(7, 0), "Europe/Vienna", "metric", "data")


def test_overrides():
    s = config.load({**GOOD, "CITY": "Graz", "POST_AT": "06:45", "TZ": "UTC",
                     "UNITS": "imperial", "DATA_DIR": "/data"})
    assert (s.city, s.post_at, str(s.tz), s.units, str(s.data_dir)) == \
        ("Graz", time(6, 45), "UTC", "imperial", "/data")


@pytest.mark.parametrize("env, says", [
    ({}, "TELEGRAM_BOT_TOKEN"),
    ({"TELEGRAM_BOT_TOKEN": "123:abc"}, "CHAT_ID"),
    ({**GOOD, "POST_AT": "7am"}, "POST_AT"),
    ({**GOOD, "TZ": "Mars/Olympus"}, "TZ"),
    ({**GOOD, "UNITS": "kelvin"}, "UNITS"),
])
def test_bad_settings_stop_with_the_fix(env, says):
    with pytest.raises(SystemExit) as e:
        config.load(env)
    assert says in str(e.value)


def test_chat_id_not_needed_for_chat_id_lookup():
    assert config.load({"TELEGRAM_BOT_TOKEN": "123:abc"}, need_chat=False).chat_id == ""


def test_token_never_in_the_repr():
    assert "123:abc" not in repr(config.load(GOOD))
