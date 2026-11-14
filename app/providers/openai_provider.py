"""Config-driven, multi-provider implementations for STT, LLM, and TTS with automatic failover."""

import io
import json
import logging
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI

from app.config import settings
from app.providers.base import STTProvider, LLMProvider, TTSProvider, LLMResponse, LLMToolCall

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Speech-to-Text (STT) Multi-Provider
# ---------------------------------------------------------------------------
class MultiProviderSTT(STTProvider):
    """Config-driven STT pipeline:
    1. Primary: Groq whisper-large-v3-turbo
    2. Fallback: Groq whisper-large-v3
    3. Tertiary: OpenAI whisper-1
    Skips any provider whose API key is missing.
    """

    def __init__(self):
        self.groq_key = (settings.GROQ_API_KEY or "").strip()
        self.openai_key = (settings.OPENAI_API_KEY or "").strip()

        self.groq_client = (
            AsyncOpenAI(base_url=settings.GROQ_BASE_URL, api_key=self.groq_key, timeout=12.0, max_retries=0)
            if self.groq_key
            else None
        )
        self.openai_client = (
            AsyncOpenAI(base_url=settings.OPENAI_BASE_URL, api_key=self.openai_key, timeout=12.0, max_retries=0)
            if self.openai_key
            else None
        )

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        if not audio_bytes:
            raise ValueError("Audio payload is empty.")

        # Candidate STT configurations: (client, model_name, label)
        candidates = []
        if self.groq_client:
            candidates.append((self.groq_client, settings.PRIMARY_STT_MODEL, "Groq (turbo)"))
            candidates.append((self.groq_client, settings.FALLBACK_STT_MODEL, "Groq (standard)"))
        if self.openai_client:
            candidates.append((self.openai_client, "whisper-1", "OpenAI Whisper"))

        if not candidates:
            logger.warning("No speech recognition API keys configured.")
            raise RuntimeError("No STT provider keys available.")

        last_error = None
        for client, model, label in candidates:
            try:
                file_obj = io.BytesIO(audio_bytes)
                file_obj.name = filename
                res = await client.audio.transcriptions.create(
                    model=model,
                    file=file_obj,
                    language="en",
                    temperature=0.0,
                )
                logger.info(f"STT successful via {label} [{model}].")
                return res.text.strip()
            except Exception as e:
                logger.warning(f"STT candidate {label} [{model}] failed: {e}")
                last_error = e

        raise RuntimeError(f"All STT providers failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# LLM Multi-Provider
# ---------------------------------------------------------------------------
class MultiProviderLLM(LLMProvider):
    """OpenAI-compatible multi-provider LLM chain:
    1. Primary: Groq (llama-3.3-70b-versatile)
    2. Fallback: Google Gemini (gemini-2.5-flash via OpenAI endpoint)
    3. Tertiary: OpenAI (gpt-4o-mini)
    Skips any provider whose API key is missing.
    """

    def __init__(self):
        self.groq_key = (settings.GROQ_API_KEY or "").strip()
        self.gemini_key = (settings.GEMINI_API_KEY or "").strip()
        self.openai_key = (settings.OPENAI_API_KEY or "").strip()

        # Build candidate providers in priority order
        self.providers = []

        if self.groq_key:
            self.providers.append({
                "label": "Groq",
                "client": AsyncOpenAI(base_url=settings.GROQ_BASE_URL, api_key=self.groq_key, timeout=12.0, max_retries=0),
                "model": settings.PRIMARY_LLM_MODEL,
            })

        if self.gemini_key:
            self.providers.append({
                "label": "Google Gemini",
                "client": AsyncOpenAI(base_url=settings.GEMINI_BASE_URL, api_key=self.gemini_key, timeout=12.0, max_retries=0),
                "model": settings.FALLBACK_LLM_MODEL,
            })

        if self.openai_key:
            self.providers.append({
                "label": "OpenAI",
                "client": AsyncOpenAI(base_url=settings.OPENAI_BASE_URL, api_key=self.openai_key, timeout=12.0, max_retries=0),
                "model": settings.TERTIARY_LLM_MODEL,
            })

    async def _call_provider(
        self,
        provider: Dict[str, Any],
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: str,
    ) -> LLMResponse:
        client: AsyncOpenAI = provider["client"]
        model: str = provider["model"]

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        completion = await client.chat.completions.create(**kwargs)
        choice = completion.choices[0]
        message = choice.message

        tool_calls: List[LLMToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except Exception:
                    args = {}
                tool_calls.append(LLMToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
        )

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        if not self.providers:
            raise RuntimeError("No LLM provider keys configured.")

        last_error = None
        for prov in self.providers:
            label = prov["label"]
            model = prov["model"]
            try:
                res = await self._call_provider(prov, messages, tools, tool_choice)
                logger.info(f"LLM completed turn successfully via {label} [{model}].")
                return res
            except Exception as e:
                logger.warning(f"LLM provider {label} [{model}] failed: {e}. Attempting next in chain...")
                last_error = e

        raise RuntimeError(f"All configured LLM providers failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Text-to-Speech (TTS) Provider with Edge-TTS & Graceful Text Fallback
# ---------------------------------------------------------------------------
class EdgeTTSProvider(TTSProvider):
    """Primary free Text-to-Speech using edge-tts.
    No API key required. Guaranteed text fallback if network fails.
    """

    def __init__(self, voice: Optional[str] = None):
        self.voice = voice or settings.EDGE_TTS_VOICE

    async def synthesize(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        if not text or not text.strip():
            return None

        clean_text = text.strip()[:800]
        selected_voice = voice or self.voice

        try:
            import edge_tts

            communicate = edge_tts.Communicate(clean_text, selected_voice)
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            audio_bytes = b"".join(chunks)
            if audio_bytes:
                return audio_bytes
        except Exception as e:
            logger.warning(f"Edge-TTS synthesis error: {e}. Falling back to text-only mode.")

        return None
