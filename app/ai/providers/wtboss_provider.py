"""
WTBoss AI Gateway provider — proxy OpenAI-compatible cho các model nội bộ
(WARP / BOSS) gồm OPS Max, Claude Opus/Sonnet, GPT 5.x, Codex…

Endpoint: https://xai.wtboss.com/v1
Tương thích chuẩn OpenAI Chat Completions / Embeddings / Vision (image_url),
do đó tái sử dụng OpenAI* client bằng cách ép base_url.

Lưu ý quan trọng: Cloudflare WAF của xai.wtboss.com chặn (403 "Your request was
blocked.") các request có User-Agent mặc định của OpenAI Python SDK
(`OpenAI/Python <ver>`). Vì vậy ở đây ta khởi tạo sẵn `openai.AsyncOpenAI` với
`default_headers` override User-Agent rồi gán vào `_inner._client` để bypass.
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

WTBOSS_BASE_URL = "https://xai.wtboss.com/v1"
WTBOSS_USER_AGENT = "wtboss-client/1.0"
_WTBOSS_DEFAULT_HEADERS = {"User-Agent": WTBOSS_USER_AGENT}


def _force_wtboss_config(config: ProviderConfig) -> ProviderConfig:
    """Trả về ProviderConfig mới ép base_url về endpoint WTBoss.

    Cho phép user override base_url qua Settings nếu muốn (ví dụ proxy nội bộ).
    """
    if config.base_url and config.base_url.strip():
        base_url = config.base_url.rstrip("/")
    else:
        base_url = WTBOSS_BASE_URL
    return ProviderConfig(
        provider=config.provider,
        api_key=config.api_key,
        model_id=config.model_id,
        base_url=base_url,
        dimensions=config.dimensions,
        extra=config.extra,
    )


def _build_wtboss_openai_client(config: ProviderConfig):
    """Tạo `openai.AsyncOpenAI` client với User-Agent custom để bypass WAF
    của xai.wtboss.com (chặn UA `OpenAI/Python`)."""
    import openai

    return openai.AsyncOpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=_WTBOSS_DEFAULT_HEADERS,
    )


class WTBossLLM(LLMProvider):
    """WTBoss LLM — wrap OpenAILLM với endpoint xai.wtboss.com/v1."""

    def __init__(self, config: ProviderConfig):
        forced = _force_wtboss_config(config)
        super().__init__(forced)
        self._inner = OpenAILLM(forced)
        self._inner._client = _build_wtboss_openai_client(forced)

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
            return False, f"WTBoss LLM error: {e}"


class WTBossEmbedding(EmbeddingProvider):
    """WTBoss Embedding — wrap OpenAIEmbedding (nếu gateway có endpoint /embeddings)."""

    def __init__(self, config: ProviderConfig):
        forced = _force_wtboss_config(config)
        super().__init__(forced)
        self._inner = OpenAIEmbedding(forced)
        self._inner._client = _build_wtboss_openai_client(forced)

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
                "WTBoss Embedding error: "
                f"{e}. Lưu ý: WTBoss tập trung cho LLM; nếu /embeddings không khả dụng, "
                "vui lòng dùng Google hoặc OpenAI cho embedding.",
            )


class WTBossVision(VisionProvider):
    """WTBoss Vision — wrap OpenAIVision (chat-completions với image_url)."""

    def __init__(self, config: ProviderConfig):
        forced = _force_wtboss_config(config)
        super().__init__(forced)
        self._inner = OpenAIVision(forced)
        self._inner._client = _build_wtboss_openai_client(forced)

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
        # Reuse OpenAIVision.test_connection — it already does a direct
        # single-shot call (no retry/swallow), so blocked/invalid-key errors
        # surface correctly through the WTBoss gateway as well.
        ok, msg = await self._inner.test_connection()
        if ok:
            return True, msg
        return False, msg.replace("OpenAI Vision error", "WTBoss Vision error")
