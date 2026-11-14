"""Abstract provider interfaces for Speech-to-Text (STT), Large Language Models (LLM), and Text-to-Speech (TTS)."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: Dict[str, Any]


class LLMResponse(BaseModel):
    content: Optional[str] = None
    tool_calls: List[LLMToolCall] = []
    finish_reason: str = "stop"


class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Converts raw audio bytes into text transcript."""
        pass


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: str = "auto",
    ) -> LLMResponse:
        """Sends chat messages and tools to the LLM and returns structured response."""
        pass


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: Optional[str] = None) -> Optional[bytes]:
        """Synthesizes text into audio bytes (e.g. MP3/WAV). Returns None if synthesis fails (triggering text fallback)."""
        pass

