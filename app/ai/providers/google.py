"""
Google Gemini provider — embedding, LLM, and vision.

Supports:
  - Embedding: gemini-embedding-2 (with task-prefix formatting)
  - LLM: gemini-2.5-flash, gemini-2.0-flash, etc.
  - Vision: gemini-2.0-flash (multimodal)
"""

import asyncio
import uuid
from typing import Optional

from loguru import logger

from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_gemini_contents,
    openai_tools_to_gemini,
)
from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)


class GoogleEmbedding(EmbeddingProvider):
    """Google Gemini embedding provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def embed(self, text: str) -> list[float]:
        from google.genai import types

        formatted = self._format_for_task(text)
        result = self.client.models.embed_content(
            model=self.config.model_id,
            contents=formatted,
            config=types.EmbedContentConfig(
                output_dimensionality=self.dimensions,
            ),
        )
        return list(result.embeddings[0].values)

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        semaphore = asyncio.Semaphore(concurrency)

        async def _embed_one(text: str) -> list[float]:
            async with semaphore:
                return await self.embed(text)

        tasks = [_embed_one(t) for t in texts]
        results = await asyncio.gather(*tasks)
        logger.debug(f"Google: embedded {len(texts)} texts (concurrency={concurrency})")
        return list(results)

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.embed("test connection")
            dim = len(result)
            return True, f"OK — model={self.config.model_id}, dimensions={dim}"
        except Exception as e:
            return False, f"Google embedding error: {e}"

    def _format_for_task(self, text: str) -> str:
        """
        Format text with task prefix for gemini-embedding-2.
        Default to document-style for ingestion.
        """
        task = self.config.extra.get("task", "document")
        if task == "search_query":
            return f"task: search result | query: {text}"
        elif task == "question_answering":
            return f"task: question answering | query: {text}"
        elif task == "document":
            return f"title: none | text: {text}"
        elif task == "classification":
            return f"task: classification | query: {text}"
        elif task == "clustering":
            return f"task: clustering | query: {text}"
        elif task == "similarity":
            return f"task: sentence similarity | query: {text}"
        return text

    def with_task(self, task: str) -> "GoogleEmbedding":
        """Return a copy with a different task type for query vs document."""
        new_config = ProviderConfig(
            provider=self.config.provider,
            api_key=self.config.api_key,
            model_id=self.config.model_id,
            base_url=self.config.base_url,
            dimensions=self.config.dimensions,
            extra={**self.config.extra, "task": task},
        )
        provider = GoogleEmbedding(new_config)
        provider._client = self._client  # Share the client
        return provider


class GoogleLLM(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        from google.genai import types

        response = self.client.models.generate_content(
            model=self.config.model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        return response.text or ""

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.2,
    ) -> AssistantTurn:
        from google.genai import types as gtypes

        contents = neutral_to_gemini_contents(messages)
        gemini_tools = openai_tools_to_gemini(tools)

        config = gtypes.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
            temperature=temperature,
            tools=gemini_tools,
            tool_config=gtypes.ToolConfig(
                function_calling_config=gtypes.FunctionCallingConfig(mode="AUTO")
            ),
        )

        response = await self.client.aio.models.generate_content(
            model=self.config.model_id,
            contents=contents,
            config=config,
        )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    text_parts.append(part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    # Gemini doesn't assign IDs — generate a stable one
                    tc_id = f"fc_{fc.name}_{uuid.uuid4().hex[:8]}"
                    tool_calls.append(ToolCall(id=tc_id, name=fc.name, arguments=args))

        finish_reason = "tool_use" if tool_calls else "end_turn"
        if response.candidates:
            fr = str(response.candidates[0].finish_reason or "")
            if "MAX_TOKENS" in fr:
                finish_reason = "max_tokens"

        # Store raw Gemini Content so neutral_to_gemini_contents can replay it
        # with thought_signature intact (required by gemini-2.5 thinking models).
        raw_content = response.candidates[0].content if response.candidates else None

        return AssistantTurn(
            text="\n".join(text_parts) or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw_provider_content=raw_content,
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Say 'OK'", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"Google LLM error: {e}"


class GoogleVision(VisionProvider):
    """Google Gemini Vision provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
    ) -> str:
        from google.genai import types

        if not prompt:
            prompt = (
                "Describe this image in detail. "
                "If it's a diagram, flowchart, or table, explain the meaning and steps. "
                "If it's a regular image, provide a concise description."
            )

        # Retry logic for transient network errors
        for attempt in range(3):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.config.model_id,
                    contents=[
                        types.Part.from_bytes(data=image_data, mime_type=mime_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=1024,
                    ),
                )
                return response.text.strip() if response.text else ""
            except Exception as e:
                logger.warning(f"Google Vision attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
        return ""

    async def test_connection(self) -> tuple[bool, str]:
        try:
            # Quick test with a tiny 1x1 PNG
            tiny_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
                b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
                b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            await self.analyze_image(tiny_png, "image/png", "What is this?")
            return True, f"OK — model={self.config.model_id}"
        except Exception as e:
            return False, f"Google Vision error: {e}"
