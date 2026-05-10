"""
OpenRouter LLM provider — proxy nhiều model thông qua một API key duy nhất.

OpenRouter dùng giao thức tương thích OpenAI, do đó tái sử dụng OpenAILLM bằng
cách ép base_url=https://openrouter.ai/api/v1 và bổ sung header HTTP-Referer
+ X-Title (khuyến nghị để OpenRouter thống kê và xếp hạng nguồn truy cập).

Tham khảo: https://openrouter.ai/docs/quick-start
"""

from typing import Optional

from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)
from app.ai.providers.openai_provider import (
    OpenAIEmbedding,
    OpenAILLM,
    OpenAIVision,
)


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://cmdsupport.com"
OPENROUTER_TITLE = "CMD Support"


def _force_openrouter_config(config: ProviderConfig) -> ProviderConfig:
    """Trả về một ProviderConfig mới đã ép base_url về endpoint OpenRouter.

    Không mutate config gốc để tránh side-effect ngoài provider.
    """
    if config.base_url and config.base_url.strip():
        base_url = config.base_url.rstrip("/")
    else:
        base_url = OPENROUTER_BASE_URL
    return ProviderConfig(
        provider=config.provider,
        api_key=config.api_key,
        model_id=config.model_id,
        base_url=base_url,
        dimensions=config.dimensions,
        extra=config.extra,
    )


class OpenRouterLLM(LLMProvider):
    """OpenRouter LLM — wraps OpenAILLM with the OpenRouter endpoint and headers."""

    def __init__(self, config: ProviderConfig):
        forced = _force_openrouter_config(config)
        super().__init__(forced)
        self._inner = OpenAILLM(forced)
        self._patch_default_headers()

    def _patch_default_headers(self) -> None:
        """Ensure OpenRouter-recommended headers are sent on every request."""
        client = self._inner.client  # AsyncOpenAI
        try:
            client.default_headers.update(
                {
                    "HTTP-Referer": OPENROUTER_REFERER,
                    "X-Title": OPENROUTER_TITLE,
                }
            )
        except Exception:
            # Older versions of openai SDK use a private dict; fail silently.
            pass

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        return await self._inner.generate(
            prompt=prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.2,
    ):
        return await self._inner.generate_with_tools(
            messages=messages,
            tools=tools,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Say 'OK'", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"OpenRouter LLM error: {e}"


def _patch_openrouter_headers(client) -> None:
    """Inject OpenRouter recommended headers on the underlying AsyncOpenAI client."""
    try:
        client.default_headers.update(
            {
                "HTTP-Referer": OPENROUTER_REFERER,
                "X-Title": OPENROUTER_TITLE,
            }
        )
    except Exception:
        pass


class OpenRouterEmbedding(EmbeddingProvider):
    """OpenRouter Embedding (OpenAI-compatible /embeddings)."""

    def __init__(self, config: ProviderConfig):
        forced = _force_openrouter_config(config)
        super().__init__(forced)
        self._inner = OpenAIEmbedding(forced)
        _patch_openrouter_headers(self._inner.client)

    async def embed(self, text: str) -> list[float]:
        return await self._inner.embed(text)

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        return await self._inner.embed_batch(texts, concurrency=concurrency)

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.embed("test connection")
            dim = len(result)
            return True, f"OK — model={self.config.model_id}, dimensions={dim}"
        except Exception as e:
            return (
                False,
                "OpenRouter Embedding error: "
                f"{e}. Lưu ý: nhiều model trên OpenRouter không cung cấp /embeddings; "
                "khuyến nghị dùng Google hoặc OpenAI cho embedding.",
            )


class OpenRouterVision(VisionProvider):
    """OpenRouter Vision (OpenAI-compatible chat-completions với image_url)."""

    def __init__(self, config: ProviderConfig):
        forced = _force_openrouter_config(config)
        super().__init__(forced)
        self._inner = OpenAIVision(forced)
        _patch_openrouter_headers(self._inner.client)

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt=None,
    ) -> str:
        return await self._inner.analyze_image(
            image_data=image_data,
            mime_type=mime_type,
            prompt=prompt,
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            tiny_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
                b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
                b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            await self.analyze_image(tiny_png, "image/png", "What is this?")
            return True, f"OK — model={self.config.model_id}"
        except Exception as e:
            return False, f"OpenRouter Vision error: {e}"
