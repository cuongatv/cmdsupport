"""
Provider Registry — central factory that resolves the correct AI provider
based on runtime configuration stored in the database.

Usage:
    registry = ProviderRegistry(db_session)

    # Embedding (for document ingestion & search)
    emb = await registry.get_embedding()
    vectors = await emb.embed_batch(["hello", "world"])

    # Embedding for queries (with search_query task for Google)
    emb_query = await registry.get_embedding(task="search_query")
    query_vec = await emb_query.embed("what is the refund policy?")

    # LLM (for summarization, webhook gateway)
    llm = await registry.get_llm()
    summary = await llm.generate("Summarize this document...")

    # Vision (for image analysis during ingestion)
    vision = await registry.get_vision()
    if vision:
        caption = await vision.analyze_image(image_bytes)
"""

from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    ProviderType,
    VisionProvider,
)

# ---------------------------------------------------------------------------
# Provider class mappings — add new providers here
# ---------------------------------------------------------------------------

def _get_embedding_class(provider: ProviderType) -> type[EmbeddingProvider]:
    if provider == ProviderType.GOOGLE:
        from app.ai.providers.google import GoogleEmbedding
        return GoogleEmbedding
    elif provider == ProviderType.OPENAI:
        from app.ai.providers.openai_provider import OpenAIEmbedding
        return OpenAIEmbedding
    elif provider == ProviderType.OPENROUTER:
        from app.ai.providers.openrouter_provider import OpenRouterEmbedding
        return OpenRouterEmbedding
    elif provider == ProviderType.WTBOSS:
        from app.ai.providers.wtboss_provider import WTBossEmbedding
        return WTBossEmbedding
    raise ValueError(f"Unsupported embedding provider: {provider}")


def _get_llm_class(provider: ProviderType) -> type[LLMProvider]:
    if provider == ProviderType.GOOGLE:
        from app.ai.providers.google import GoogleLLM
        return GoogleLLM
    elif provider == ProviderType.OPENAI:
        from app.ai.providers.openai_provider import OpenAILLM
        return OpenAILLM
    elif provider == ProviderType.ANTHROPIC:
        from app.ai.providers.anthropic_provider import AnthropicLLM
        return AnthropicLLM
    elif provider == ProviderType.OPENROUTER:
        from app.ai.providers.openrouter_provider import OpenRouterLLM
        return OpenRouterLLM
    elif provider == ProviderType.WTBOSS:
        from app.ai.providers.wtboss_provider import WTBossLLM
        return WTBossLLM
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _get_vision_class(provider: ProviderType) -> type[VisionProvider]:
    if provider == ProviderType.GOOGLE:
        from app.ai.providers.google import GoogleVision
        return GoogleVision
    elif provider == ProviderType.OPENAI:
        from app.ai.providers.openai_provider import OpenAIVision
        return OpenAIVision
    elif provider == ProviderType.OPENROUTER:
        from app.ai.providers.openrouter_provider import OpenRouterVision
        return OpenRouterVision
    elif provider == ProviderType.WTBOSS:
        from app.ai.providers.wtboss_provider import WTBossVision
        return WTBossVision
    raise ValueError(f"Unsupported vision provider: {provider}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """
    Resolves provider configs from DB and returns the correct implementation.

    Config keys in DB follow the pattern: {capability}_{field}
      - embedding_provider, embedding_model_id, embedding_api_key, ...
      - llm_provider, llm_model_id, llm_api_key, ...
      - vision_provider, vision_model_id, vision_api_key, ...
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_embedding(self, task: str = "document") -> EmbeddingProvider:
        """
        Get the configured embedding provider.

        Args:
            task: Embedding task type. Some providers (Google) use this to
                  optimize embeddings for different use cases.
                  - "document" for document chunks during ingestion
                  - "search_query" for user queries during search
        """
        config = await self._load_config("embedding")
        config.extra["task"] = task
        cls = _get_embedding_class(config.provider)
        return cls(config)

    async def get_llm(self) -> LLMProvider:
        """Get the configured LLM provider."""
        config = await self._load_config("llm")
        cls = _get_llm_class(config.provider)
        return cls(config)

    async def get_vision(self) -> Optional[VisionProvider]:
        """Get the configured vision provider. Returns None if not configured."""
        try:
            config = await self._load_config("vision")
            cls = _get_vision_class(config.provider)
            return cls(config)
        except ValueError:
            logger.debug("No vision provider configured, image analysis disabled")
            return None

    async def test_all(self) -> dict[str, tuple[bool, str]]:
        """
        Test all configured providers.
        Returns: {"embedding": (True, "OK"), "llm": (False, "error"), ...}
        """
        results = {}

        for capability in ("embedding", "llm", "vision"):
            try:
                config = await self._load_config(capability)
            except ValueError as e:
                results[capability] = (False, f"Not configured: {e}")
                continue

            try:
                if capability == "embedding":
                    provider = _get_embedding_class(config.provider)(config)
                elif capability == "llm":
                    provider = _get_llm_class(config.provider)(config)
                else:
                    provider = _get_vision_class(config.provider)(config)
                results[capability] = await provider.test_connection()
            except Exception as e:
                results[capability] = (False, str(e))

        return results

    # --- Internal ---

    async def _load_config(self, capability: str) -> ProviderConfig:
        """Load provider config from DB for a given capability."""
        from app.services.config_service import ConfigService
        svc = ConfigService(self.db)

        provider_str = await svc.get(f"{capability}_provider")
        model_id = await svc.get(f"{capability}_model_id")
        api_key = await svc.get(f"{capability}_api_key")
        base_url = await svc.get(f"{capability}_base_url")
        dimensions_str = await svc.get(f"{capability}_dimensions")

        if not provider_str or not model_id:
            raise ValueError(
                f"No {capability} provider configured. "
                f"Set {capability}_provider and {capability}_model_id in settings."
            )

        return ProviderConfig(
            provider=ProviderType(provider_str),
            api_key=api_key or "",
            model_id=model_id,
            base_url=base_url,
            dimensions=int(dimensions_str) if dimensions_str else None,
            extra={},
        )


# ---------------------------------------------------------------------------
# Convenience: supported providers list (for admin UI dropdowns)
# ---------------------------------------------------------------------------

SUPPORTED_PROVIDERS = {
    "embedding": [
        {"id": "google", "name": "Google Gemini", "models": [
            "gemini-embedding-2", "text-embedding-004",
        ]},
        {"id": "openai", "name": "OpenAI", "models": [
            "text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002",
        ]},
        {"id": "openrouter", "name": "OpenRouter", "models": [
            "openai/text-embedding-3-small",
            "openai/text-embedding-3-large",
        ]},
        {"id": "wtboss", "name": "WTBoss AI Gateway", "models": []},
    ],
    "llm": [
        {"id": "google", "name": "Google Gemini", "models": [
            "gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro",
        ]},
        {"id": "openai", "name": "OpenAI", "models": [
            "gpt-4o", "gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano",
        ]},
        {"id": "anthropic", "name": "Anthropic", "models": [
            "claude-sonnet-4-20250514", "claude-haiku-4-20250514",
        ]},
        {"id": "openrouter", "name": "OpenRouter", "models": [
            "openai/gpt-4o-mini",
            "openai/gpt-4o",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.5-haiku",
            "google/gemini-2.0-flash-001",
            "google/gemini-2.5-pro",
            "meta-llama/llama-3.3-70b-instruct",
            "deepseek/deepseek-chat",
            "mistralai/mistral-large",
            "qwen/qwen-2.5-72b-instruct",
        ]},
        {"id": "wtboss", "name": "WTBoss AI Gateway", "models": [
            "warp/ops-max-fast",
            "warp/claude-opus-4-7",
            "warp/claude-opus-4-6",
            "warp/claude-sonnet-4-6",
            "warp/gpt-5.4",
            "warp/gpt-5.4-mini",
            "warp/gpt-5.3-codex",
            "boss/gpt-5.5",
            "boss/gpt-5.4",
            "boss/gpt-5.4-mini",
            "boss/gpt-5.3-codex",
        ]},
    ],
    "vision": [
        {"id": "google", "name": "Google Gemini", "models": [
            "gemini-2.0-flash", "gemini-2.5-flash",
        ]},
        {"id": "openai", "name": "OpenAI", "models": [
            "gpt-4o", "gpt-4o-mini",
        ]},
        {"id": "openrouter", "name": "OpenRouter", "models": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash-001",
        ]},
        {"id": "wtboss", "name": "WTBoss AI Gateway", "models": [
            "warp/claude-opus-4-7",
            "warp/claude-sonnet-4-6",
            "warp/gpt-5.4",
            "boss/gpt-5.5",
        ]},
    ],
}
