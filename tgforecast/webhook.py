"""The answer bot's webhook: python-telegram-bot's own server reads a whole request body (up to
100 MB) before it looks at the secret header, which a free 512 MB instance cannot afford. This
one checks the secret first, then the size, then reads — the "custom webhook" setup the
python-telegram-bot docs describe."""

from __future__ import annotations

import hmac
import json
import logging
from collections import deque

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from telegram import Update
from telegram.ext import Application

log = logging.getLogger(__name__)

MAX_BODY = 1_000_000  # bytes; a Telegram update is a few KB
SEEN = 1000  # update ids remembered, so Telegram's retries are answered once


def make_app(ptb: Application, secret: str, max_body: int = MAX_BODY, path: str = "telegram"):
    seen: deque[int] = deque(maxlen=SEEN)

    async def telegram(request: Request) -> Response:
        given = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(given.encode(), secret.encode()):
            return Response(status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > max_body:
                return Response(status_code=413)
        except ValueError:
            return Response(status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > max_body:
                return Response(status_code=413)
        try:
            data = json.loads(body)
            update_id = data["update_id"]
        except (ValueError, KeyError, TypeError):
            return Response(status_code=400)
        if update_id not in seen:
            try:
                update = Update.de_json(data, ptb.bot)
            except Exception as e:  # noqa: BLE001 — its message may quote the user's text
                log.warning("update %s dropped, not parsed: %s", update_id, type(e).__name__)
                seen.append(update_id)
                return Response()  # a 4xx only makes Telegram send it again
            seen.append(update_id)
            await ptb.update_queue.put(update)
        return Response()

    async def health(request: Request) -> Response:
        return Response("ok")

    return Starlette(
        routes=[
            Route(f"/{path}", telegram, methods=["POST"]),
            Route("/health", health, methods=["GET"]),
        ]
    )


async def serve(ptb: Application, *, port: int, url: str, secret: str, path: str) -> None:
    """Run the bot behind make_app until the process is stopped."""
    server = uvicorn.Server(
        uvicorn.Config(
            make_app(ptb, secret, path=path), host="0.0.0.0", port=port, log_level="warning"
        )
    )
    async with ptb:  # initialize / shutdown
        if ptb.post_init:
            await ptb.post_init(ptb)
        await ptb.bot.set_webhook(
            url=url,
            secret_token=secret,
            allowed_updates=["message"],
            drop_pending_updates=False,  # the message that woke the service gets its answer
        )
        await ptb.start()
        try:
            await server.serve()
        finally:
            await ptb.stop()
            if ptb.post_shutdown:
                await ptb.post_shutdown(ptb)
