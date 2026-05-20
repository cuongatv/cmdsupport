# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations


class TelegramRateLimitError(Exception):
    retry_after: int

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(message or f"Telegram rate limited; retry after {retry_after}s")


class FakeTelegramClient:
    next_response_status: int
    retry_after: int | None
    bot_info: dict[str, object]
    sent: list[dict[str, object]]
    webhooks_set: list[dict[str, object]]
    webhooks_deleted: list[bool]
    _message_id: int

    def __init__(
        self,
        *,
        next_response_status: int = 200,
        retry_after: int | None = None,
        bot_info: dict[str, object] | None = None,
    ) -> None:
        self.next_response_status = next_response_status
        self.retry_after = retry_after
        self.bot_info = bot_info or {
            "ok": True,
            "result": {
                "id": 7777,
                "username": "CMDSupportBot",
                "is_bot": True,
            },
        }
        self.sent = []
        self.webhooks_set = []
        self.webhooks_deleted = []
        self._message_id = 0

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        if self.retry_after is not None:
            raise TelegramRateLimitError(self.retry_after)

        self._message_id += 1
        record: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "message_thread_id": message_thread_id,
            "message_id": self._message_id,
            "response_status": self.next_response_status,
        }
        self.sent.append(record)
        return {"ok": True, "result": {"message_id": self._message_id}}

    async def set_webhook(self, url: str, secret_token: str) -> dict[str, object]:
        record: dict[str, object] = {"url": url, "secret_token": secret_token}
        self.webhooks_set.append(record)
        return {"ok": True, "result": True}

    async def delete_webhook(self) -> dict[str, object]:
        self.webhooks_deleted.append(True)
        return {"ok": True, "result": True}

    async def get_me(self) -> dict[str, object]:
        return self.bot_info
