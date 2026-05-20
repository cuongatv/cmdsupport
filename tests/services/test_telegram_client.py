# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportUnknownLambdaType=false
from __future__ import annotations

import json

import httpx
import pytest
from loguru import logger

from app.integrations.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramRateLimitError,
)

pytestmark = pytest.mark.asyncio


class _RequestRecorder:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.responses: list[tuple[int, dict[str, object]]] = []

    def add_response(self, status_code: int, payload: dict[str, object]) -> None:
        self.responses.append((status_code, payload))

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.read()
        parsed_body = json.loads(body.decode()) if body else {}
        self.requests.append(
            {
                "method": request.method,
                "url": str(request.url),
                "body": parsed_body,
            }
        )
        status_code, payload = self.responses.pop(0)
        return httpx.Response(status_code, json=payload)


async def _make_client(recorder: _RequestRecorder, token: str = "BOT_TOKEN") -> TelegramClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    return TelegramClient(token=token, http_client=http_client)


async def test_send_message_happy_path_posts_json_and_returns_result_dict() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(200, {"ok": True, "result": {"message_id": 123}})
    client = await _make_client(recorder)

    try:
        result = await client.send_message(12345, "Hello", parse_mode="HTML")
    finally:
        await client.aclose()

    assert result == {"message_id": 123}
    assert recorder.requests == [
        {
            "method": "POST",
            "url": "https://api.telegram.org/botBOT_TOKEN/sendMessage",
            "body": {
                "chat_id": 12345,
                "text": "Hello",
                "parse_mode": "HTML",
            },
        }
    ]


async def test_send_message_forwards_escaped_text_verbatim() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(200, {"ok": True, "result": {"message_id": 124}})
    client = await _make_client(recorder)

    try:
        await client.send_message(12345, "&lt;b&gt;safe&lt;/b&gt;", parse_mode="HTML")
    finally:
        await client.aclose()

    assert recorder.requests[0]["body"] == {
        "chat_id": 12345,
        "text": "&lt;b&gt;safe&lt;/b&gt;",
        "parse_mode": "HTML",
    }


async def test_send_message_429_raises_rate_limit_error() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(
        429,
        {
            "ok": False,
            "description": "Too Many Requests: retry later",
            "parameters": {"retry_after": 17},
        },
    )
    client = await _make_client(recorder)

    try:
        with pytest.raises(TelegramRateLimitError) as excinfo:
            await client.send_message(12345, "Hello")
    finally:
        await client.aclose()

    assert excinfo.value.retry_after == 17
    assert excinfo.value.parameters == {"retry_after": 17}


async def test_send_message_403_raises_api_error() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(403, {"ok": False, "description": "Forbidden: bot was kicked"})
    client = await _make_client(recorder)

    try:
        with pytest.raises(TelegramAPIError) as excinfo:
            await client.send_message(12345, "Hello")
    finally:
        await client.aclose()

    assert excinfo.value.status_code == 403
    assert excinfo.value.description == "Forbidden: bot was kicked"


async def test_set_webhook_posts_url_and_secret_token() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(200, {"ok": True, "result": True})
    client = await _make_client(recorder)

    try:
        await client.set_webhook(
            "https://example.com/telegram/webhook",
            secret_token="HOOK_SECRET",
            allowed_updates=["message", "edited_message"],
        )
    finally:
        await client.aclose()

    assert recorder.requests[0]["url"] == "https://api.telegram.org/botBOT_TOKEN/setWebhook"
    assert recorder.requests[0]["body"] == {
        "url": "https://example.com/telegram/webhook",
        "secret_token": "HOOK_SECRET",
        "allowed_updates": ["message", "edited_message"],
    }


async def test_get_me_returns_bot_info_dict() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(
        200,
        {
            "ok": True,
            "result": {"id": 7777, "username": "CMDSupportBot", "is_bot": True},
        },
    )
    client = await _make_client(recorder)

    try:
        result = await client.get_me()
    finally:
        await client.aclose()

    assert result == {"id": 7777, "username": "CMDSupportBot", "is_bot": True}


async def test_telegram_logs_do_not_include_token() -> None:
    recorder = _RequestRecorder()
    recorder.add_response(
        429,
        {
            "ok": False,
            "description": "Too Many Requests: retry later",
            "parameters": {"retry_after": 3},
        },
    )
    client = await _make_client(recorder, token="SUPER_SECRET_TOKEN")
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]), level="DEBUG")

    try:
        with pytest.raises(TelegramRateLimitError):
            await client.send_message(12345, "Hello")
    finally:
        logger.remove(sink_id)
        await client.aclose()

    assert all("SUPER_SECRET_TOKEN" not in message for message in messages)
