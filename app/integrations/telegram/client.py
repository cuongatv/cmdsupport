# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false
from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import httpx
from loguru import logger


class TelegramAPIError(Exception):
    status_code: int
    description: str | None
    parameters: dict[str, object] | None

    def __init__(
        self,
        status_code: int,
        description: str | None = None,
        parameters: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.description = description
        self.parameters = parameters
        super().__init__(description or f"Telegram API error {status_code}")


class TelegramRateLimitError(TelegramAPIError):
    retry_after: int

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(
            429,
            description=message or f"Telegram rate limited; retry after {retry_after}s",
            parameters={"retry_after": retry_after},
        )


class TelegramClient:
    _token: str
    _base_url: str
    _http_client: httpx.AsyncClient
    _owns_http_client: bool

    def __init__(
        self,
        *,
        token: str,
        base_url: str = "https://api.telegram.org",
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
        disable_web_page_preview: bool = True,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if not disable_web_page_preview:
            payload["disable_web_page_preview"] = disable_web_page_preview
        return self._result_dict(
            await self._request("sendMessage", json=payload),
        )

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return self._result_dict(await self._request("editMessageText", json=payload))

    async def set_webhook(
        self,
        url: str,
        *,
        secret_token: str,
        allowed_updates: list[str] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"url": url, "secret_token": secret_token}
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        return self._result_dict(await self._request("setWebhook", json=payload))

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {}
        if drop_pending_updates:
            payload["drop_pending_updates"] = drop_pending_updates
        return self._result_dict(await self._request("deleteWebhook", json=payload))

    async def get_me(self) -> dict[str, object]:
        return self._result_dict(await self._request("getMe"))

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def _request(self, method: str, **kwargs: object) -> dict[str, object]:
        url = f"{self._base_url}/bot{self._token}/{method}"
        logger.debug("Telegram API request {} started", method)
        response = await self._http_client.post(url, **kwargs)
        payload = self._response_payload(response)

        if response.status_code == 429:
            retry_after = self._retry_after(payload)
            logger.warning(
                "Telegram API rate limited for method {} retry_after={}",
                method,
                retry_after,
            )
            raise TelegramRateLimitError(retry_after, self._description(payload))

        if response.status_code != 200:
            logger.warning(
                "Telegram API request {} failed with status {}",
                method,
                response.status_code,
            )
            raise TelegramAPIError(
                status_code=response.status_code,
                description=self._description(payload),
                parameters=self._parameters(payload),
            )

        if payload.get("ok") is False:
            logger.warning("Telegram API request {} returned ok=false", method)
            raise TelegramAPIError(
                status_code=response.status_code,
                description=self._description(payload),
                parameters=self._parameters(payload),
            )

        logger.debug(
            "Telegram API request {} completed with status {}",
            method,
            response.status_code,
        )
        return payload

    @staticmethod
    def _response_payload(response: httpx.Response) -> dict[str, object]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        if isinstance(payload, dict):
            return cast(dict[str, object], payload)
        return {}

    @staticmethod
    def _description(payload: Mapping[str, object]) -> str | None:
        description = payload.get("description")
        return description if isinstance(description, str) else None

    @staticmethod
    def _parameters(payload: Mapping[str, object]) -> dict[str, object] | None:
        parameters = payload.get("parameters")
        return cast(dict[str, object], parameters) if isinstance(parameters, dict) else None

    @staticmethod
    def _retry_after(payload: Mapping[str, object]) -> int:
        parameters = TelegramClient._parameters(payload)
        if parameters is None:
            return 0
        retry_after = parameters.get("retry_after")
        if isinstance(retry_after, bool):
            return 0
        if isinstance(retry_after, int):
            return retry_after
        if isinstance(retry_after, str):
            try:
                return int(retry_after)
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _result_dict(payload: Mapping[str, object]) -> dict[str, object]:
        result = payload.get("result")
        if isinstance(result, dict):
            return cast(dict[str, object], result)
        if isinstance(result, Mapping):
            return cast(dict[str, object], dict(result))
        return {"result": result}
