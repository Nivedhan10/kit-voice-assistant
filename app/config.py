"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # College System API
    COLLEGE_API_KEY: str = Field(default="")
    COLLEGE_API_BASE_URL: str = Field(default="https://ht.knowvally.com")

    # AI Provider API Keys
    GROQ_API_KEY: Optional[str] = Field(default=None)
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_KEY: Optional[str] = Field(default=None)

    # Provider Endpoints & Models (Config-Driven)
    GROQ_BASE_URL: str = Field(default="https://api.groq.com/openai/v1")
    GEMINI_BASE_URL: str = Field(default="https://generativelanguage.googleapis.com/v1beta/openai")
    OPENAI_BASE_URL: str = Field(default="https://api.openai.com/v1")

    # Primary & Fallback LLM Models
    PRIMARY_LLM_MODEL: str = Field(default="openai/gpt-oss-120b")
    FALLBACK_LLM_MODEL: str = Field(default="openai/gpt-oss-20b")
    TERTIARY_LLM_MODEL: str = Field(default="gpt-4o-mini")

    # STT Models
    PRIMARY_STT_MODEL: str = Field(default="whisper-large-v3-turbo")
    FALLBACK_STT_MODEL: str = Field(default="whisper-large-v3")

    # TTS Settings
    TTS_PROVIDER: str = Field(default="edge_tts")  # "edge_tts" | "openai"
    EDGE_TTS_VOICE: str = Field(default="en-US-JennyNeural")
    OPENAI_TTS_VOICE: str = Field(default="alloy")

    # Security & Session
    SESSION_SECRET_KEY: str = Field(default="kit-voice-assistant-production-secret-2026")
    SESSION_COOKIE_NAME: str = Field(default="kit_session_id")
    SESSION_MAX_AGE_SECONDS: int = Field(default=28800)  # 8 hours matching college token

    # Persistence
    DATABASE_URL: str = Field(default="sqlite:///./kit_assistant.db")

    # College Academic Rules & Thresholds (from Handbook 2026 & Circular 12/2026)
    MIN_ATTENDANCE_PERCENT: float = Field(default=75.0)
    LAB_MIN_ATTENDANCE_PERCENT: float = Field(default=80.0)
    MAX_OD_DAYS_PER_SEMESTER: int = Field(default=10)
    OD_PROOF_DEADLINE_DAYS: int = Field(default=3)  # Overridden by Circular 12/2026 from 5 to 3
    LEAVE_NOTICE_HOURS: int = Field(default=24)      # Must apply >= 24h before personal leave starts

    # Request Guardrails
    MAX_AUDIO_SIZE_BYTES: int = Field(default=10 * 1024 * 1024)  # 10 MB limit
    MAX_AGENT_STEPS: int = Field(default=5)
    CONFIRMATION_TIMEOUT_SECONDS: int = Field(default=120)


settings = Settings()
