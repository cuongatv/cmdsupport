"""
OpenAI provider — embedding, LLM, and vision.

Supports:
  - Embedding: text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002
  - LLM: gpt-4o, gpt-4o-mini, gpt-3.5-turbo, etc.
  - Vision: gpt-4o (multimodal)

Also works with any OpenAI-compatible API (Azure, Together, Groq, etc.)
by setting a custom base_url.
"""

import asyncio
import base64
import json
from typing import Optional

from loguru import logger

from app.ai.agent_protocol import (
    AssistantTurn,
    ToolCall,
    neutral_to_openai_messages,
)
from app.ai.providers.base import (
    EmbeddingProvider,
    LLMProvider,
    ProviderConfig,
    VisionProvider,
)


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI embedding provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,  # None = default OpenAI
            )
        return self._client

    async def embed(self, text: str) -> list[float]:
        kwargs = {
            "model": self.config.model_id,
            "input": text,
        }
        # text-embedding-3-* supports custom dimensions
        if self.config.dimensions:
            kwargs["dimensions"] = self.dimensions

        response = await self.client.embeddings.create(**kwargs)
        return response.data[0].embedding

    async def embed_batch(
        self, texts: list[str], concurrency: int = 5
    ) -> list[list[float]]:
        # OpenAI supports batch input natively (up to 2048 items)
        # Split into batches of 100 for safety
        batch_size = 100
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            kwargs = {
                "model": self.config.model_id,
                "input": batch,
            }
            if self.config.dimensions:
                kwargs["dimensions"] = self.dimensions

            response = await self.client.embeddings.create(**kwargs)
            # Sort by index to maintain order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([d.embedding for d in sorted_data])

        logger.debug(f"OpenAI: embedded {len(texts)} texts in batches of {batch_size}")
        return all_embeddings

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.embed("test connection")
            dim = len(result)
            return True, f"OK — model={self.config.model_id}, dimensions={dim}"
        except Exception as e:
            return False, f"OpenAI embedding error: {e}"


class OpenAILLM(LLMProvider):
    """OpenAI LLM provider."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.2,
    ) -> AssistantTurn:
        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(neutral_to_openai_messages(messages))

        response = await self.client.chat.completions.create(
            model=self.config.model_id,
            messages=openai_messages,
            tools=tools,  # already in OpenAI format
            max_tokens=max_tokens,
            temperature=temperature,
        )

        choice = response.choices[0]
        message = choice.message
        text = message.content
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args: dict = {}
                if tc.function.arguments:
                    try:
                        args = json.loads(tc.function.arguments)
                    except Exception:
                        pass
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        reason_map = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens"}
        finish_reason = reason_map.get(choice.finish_reason or "stop", "end_turn")

        return AssistantTurn(
            text=text or None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )

    async def test_connection(self) -> tuple[bool, str]:
        try:
            result = await self.generate("Say 'OK'", max_tokens=10, temperature=0)
            return True, f"OK — model={self.config.model_id}, response='{result[:50]}'"
        except Exception as e:
            return False, f"OpenAI LLM error: {e}"


class OpenAIVision(VisionProvider):
    """OpenAI Vision provider (GPT-4o multimodal)."""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._client

    async def analyze_image(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        prompt: Optional[str] = None,
    ) -> str:
        if not prompt:
            prompt = (
                "Describe this image in detail. "
                "If it's a diagram, flowchart, or table, explain the meaning and steps. "
                "If it's a regular image, provide a concise description."
            )

        b64_image = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64_image}"

        for attempt in range(3):
            try:
                response = await self.client.chat.completions.create(
                    model=self.config.model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_url, "detail": "low"},
                                },
                            ],
                        }
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                logger.warning(f"OpenAI Vision attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)
        return ""

    async def test_connection(self) -> tuple[bool, str]:
        # Direct one-shot call WITHOUT the retry-and-swallow logic in
        # analyze_image() so genuine errors (auth, blocked, model not found)
        # surface to the user instead of returning a false-positive OK.
        try:
            tiny_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
                b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
                b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            data_url = f"data:image/png;base64,{base64.b64encode(tiny_png).decode('utf-8')}"
            response = await self.client.chat.completions.create(
                model=self.config.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What is this?"},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url, "detail": "low"},
                            },
                        ],
                    }
                ],
                max_tokens=16,
                temperature=0,
            )
            _ = response.choices[0].message.content or ""
            return True, f"OK — model={self.config.model_id}"
        except Exception as e:
            return False, f"OpenAI Vision error: {e}"
