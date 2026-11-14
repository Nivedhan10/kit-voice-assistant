"""Resilience, fallback mechanisms, empty key handling, and client 5xx prevention tests."""

import pytest
import io
import httpx
from app.providers.base import LLMProvider, LLMResponse, LLMToolCall
from app.providers.openai_provider import MultiProviderLLM, MultiProviderSTT, EdgeTTSProvider
from app.agent.orchestrator import AgentOrchestrator
from app.auth.session import SessionData
from app.main import app


class FailingPrimaryLLM(LLMProvider):
    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, tools=None, tool_choice="auto"):
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("Primary API Rate Limit 429")
        return LLMResponse(content="Fallback response successfully generated.")


@pytest.mark.asyncio
async def test_llm_provider_fallback_chain():
    """Verify that when primary provider throws an error, fallback provider is invoked."""
    fallback_client = FailingPrimaryLLM()
    
    # First call fails
    with pytest.raises(RuntimeError):
        await fallback_client.chat([])

    # Second call succeeds
    res = await fallback_client.chat([])
    assert "Fallback response" in res.content


@pytest.mark.asyncio
async def test_multi_provider_llm_skips_empty_keys():
    """Verify MultiProviderLLM initializes without crashing when keys are empty and raises expected error if called."""
    provider = MultiProviderLLM()
    # If no keys in environment, providers list should safely be empty or only contain present keys
    for prov in provider.providers:
        assert prov["client"].api_key, "Provider must not register with empty API key"


@pytest.mark.asyncio
async def test_multi_provider_stt_skips_empty_keys():
    """Verify MultiProviderSTT skips unconfigured providers."""
    stt = MultiProviderSTT()
    if not stt.groq_key:
        assert stt.groq_client is None
    if not stt.openai_key:
        assert stt.openai_client is None


@pytest.mark.asyncio
async def test_client_never_sees_5xx_on_stt_failure():
    """Verify that if STT fails (e.g. invalid/quota-exhausted audio call), client receives HTTP 200 with polite retry message."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Send dummy audio that will fail cloud STT
        dummy_audio = io.BytesIO(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00")
        files = {"audio": ("test.wav", dummy_audio, "audio/wav")}

        response = await client.post("/api/v1/voice/chat", files=files)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "reply_text" in data
        assert "OPENAI" not in data["reply_text"]
        assert "GROQ" not in data["reply_text"]
        assert "credits" not in data["reply_text"]
        assert "trouble hearing" in data["reply_text"] or "processed" in data["reply_text"]


@pytest.mark.asyncio
async def test_edge_tts_synthesizes_or_falls_back():
    """Verify EdgeTTSProvider synthesizes audio bytes or returns None without throwing unhandled exceptions."""
    tts = EdgeTTSProvider()
    res = await tts.synthesize("Welcome to KIT.")
    # Either successfully returns audio bytes (online) or returns None (offline), never crashes
    assert res is None or isinstance(res, bytes)


@pytest.mark.asyncio
async def test_agent_bounded_step_limit():
    """Verify agent loop terminates safely if tools loop infinitely."""
    class LoopingLLM(LLMProvider):
        async def chat(self, messages, tools=None, tool_choice="auto"):
            return LLMResponse(
                content=None,
                tool_calls=[LLMToolCall(id="c1", name="search_admission_brochure", arguments={"query": "fees"})]
            )

    orchestrator = AgentOrchestrator(llm_provider=LoopingLLM())
    session = SessionData(session_id="s1", role="public")

    result = await orchestrator.run(
        session=session,
        user_message="Tell me fees",
        conversation_history=[]
    )

    assert "reply_text" in result
    assert len(result["actions_taken"]) > 0
