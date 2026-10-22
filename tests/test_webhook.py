import asyncio
import json

import pytest
from starlette.testclient import TestClient

from tgforecast import webhook

SECRET = "s3cret"
UPDATE = {"update_id": 7}


class FakePTB:
    def __init__(self):
        self.update_queue = asyncio.Queue()
        self.bot = None


@pytest.fixture
def ptb():
    return FakePTB()


@pytest.fixture
def client(ptb):
    return TestClient(webhook.make_app(ptb, SECRET, max_body=1000))


def post(client, body, secret=SECRET, **headers):
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return client.post("/telegram", content=body, headers=headers)


def test_a_wrong_or_missing_secret_is_refused_before_the_body_is_read(client, ptb):
    def never():
        raise AssertionError("the body was read")
        yield b""

    assert (
        client.post(
            "/telegram", content=never(), headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}
        ).status_code
        == 403
    )
    assert post(client, json.dumps(UPDATE), secret=None).status_code == 403
    assert ptb.update_queue.empty()


def test_an_oversized_body_is_refused(client, ptb):
    assert post(client, b"x" * 2000).status_code == 413
    chunks = (b"x" * 400 for _ in range(4))  # no Content-Length: counted while reading
    assert post(client, chunks).status_code == 413
    assert ptb.update_queue.empty()


def test_a_valid_update_is_queued_once(client, ptb):
    assert post(client, json.dumps(UPDATE)).status_code == 200
    assert post(client, json.dumps(UPDATE)).status_code == 200  # Telegram's retry
    assert ptb.update_queue.qsize() == 1
    assert ptb.update_queue.get_nowait().update_id == 7


def test_not_json_is_a_bad_request(client, ptb):
    assert post(client, b"{nope").status_code == 400
    assert ptb.update_queue.empty()


def test_an_update_telegram_cannot_parse_is_dropped_once_and_logs_no_text(
    client, ptb, caplog, monkeypatch
):
    # Not 4xx: Telegram retries a refused update until it gives up, waking the free host
    # each time, and parsing it again will not succeed.
    def broken(data, bot):
        raise TypeError(f"cannot parse {data}")

    monkeypatch.setattr(webhook.Update, "de_json", broken)
    body = json.dumps({"update_id": 8, "message": {"text": "Graz secret"}})
    assert post(client, body).status_code == 200
    assert "Graz secret" not in caplog.text
    assert ptb.update_queue.empty()


def test_health(client):
    assert client.get("/health").status_code == 200
