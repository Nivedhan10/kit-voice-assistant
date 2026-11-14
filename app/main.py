"""Main FastAPI application for Knotopian Institute of Technology (KIT) Real-Time Voice Assistant."""

import base64
import logging
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, status, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.auth.session import session_manager, SessionData
from app.auth.dependencies import get_session, require_authenticated
from app.college_api.client import college_client, CollegeAPIError
from app.providers.openai_provider import MultiProviderSTT, MultiProviderLLM, EdgeTTSProvider
from app.agent.orchestrator import AgentOrchestrator
from app.history.store import history_store

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kit_assistant")

app = FastAPI(
    title="Knotopian Institute of Technology (KIT) Voice Assistant",
    description="Production-grade real-time voice assistant with RBAC and academic rule enforcement.",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Initialize Multi-Provider Speech & AI Engine
stt_provider = MultiProviderSTT()
llm_provider = MultiProviderLLM()
tts_provider = EdgeTTSProvider()
agent_orchestrator = AgentOrchestrator(llm_provider=llm_provider)


# --- Models ---
class LoginPayload(BaseModel):
    login_id: str
    password: str


# --- Pages ---
@app.get("/", response_class=HTMLResponse)
async def home_page():
    with open("app/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/portal", response_class=HTMLResponse)
async def portal_page():
    with open("app/static/portal.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/history", response_class=HTMLResponse)
async def history_page():
    with open("app/static/history.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# --- Health Check ---
@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "KIT Real-Time Voice Assistant",
        "version": "1.0.0",
        "tts_provider": "edge_tts",
        "college_system": settings.COLLEGE_API_BASE_URL,
    }


# --- Authentication Endpoints ---
@app.post("/api/v1/auth/login")
async def login(payload: LoginPayload, response: Response):
    try:
        login_res = await college_client.login(login_id=payload.login_id, password=payload.password)
        user_info = login_res.user.model_dump()
        token = login_res.access_token

        # Create authenticated server session (token never leaves server)
        session = session_manager.create_authenticated_session(college_token=token, user_info=user_info)

        # Set secure httpOnly cookie
        signed_cookie = session_manager._sign(session.session_id)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=signed_cookie,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=False,
        )

        return {
            "success": True,
            "user": {
                "id": session.user_id,
                "login_id": session.login_id,
                "full_name": session.full_name,
                "role": session.role,
                "class_code": session.class_code,
                "department": session.department,
            }
        }
    except CollegeAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed. Please verify credentials.")


@app.post("/api/v1/auth/logout")
async def logout(response: Response, session: SessionData = Depends(get_session)):
    session_manager.delete_session(session.session_id)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME)
    return {"success": True, "message": "Logged out successfully."}


@app.get("/api/v1/auth/me")
async def get_me(session: SessionData = Depends(get_session)):
    return {
        "authenticated": session.is_authenticated(),
        "session_id": session.session_id,
        "user_id": session.user_id,
        "login_id": session.login_id,
        "full_name": session.full_name,
        "role": session.role,
        "class_code": session.class_code,
        "department": session.department,
    }


# --- Core Voice Assistant Endpoint ---
@app.post("/api/v1/voice/chat")
async def voice_chat(
    audio: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    session: SessionData = Depends(get_session),
):
    """Processes user voice interaction through external STT -> Agent ReAct -> TTS.
    Web Speech API is strictly NOT used.
    """
    transcript = ""

    # 1. Speech-to-Text via External Speech Service
    if audio:
        content = await audio.read()
        if len(content) > settings.MAX_AUDIO_SIZE_BYTES:
            raise HTTPException(status_code=413, detail="Audio file exceeds 10MB limit.")
        try:
            transcript = await stt_provider.transcribe(content, filename=audio.filename or "audio.webm")
        except Exception as stt_err:
            logger.error(f"STT Error (logged server-side only): {stt_err}")
            # Friendly, production-grade error response without leaking keys or config
            return {
                "transcript": "[Voice received]",
                "reply_text": "I am having trouble hearing your audio clearly right now. Please try speaking again, or click one of the quick options below.",
                "audio_base64": None,
                "actions_taken": [],
                "pending_action": None,
                "conversation_id": None,
            }
    elif text:
        transcript = text.strip()
    else:
        raise HTTPException(status_code=400, detail="Either audio file or text must be provided.")

    if not transcript:
        return {
            "transcript": "",
            "reply_text": "I didn't catch that. Could you please repeat?",
            "audio_base64": None,
            "actions_taken": [],
            "pending_action": None,
        }

    # 2. Retrieve Conversation Context & History
    conv_id = history_store.get_or_create_active_conversation(
        session_id=session.session_id,
        role=session.role,
        user_id=str(session.user_id) if session.user_id else None
    )
    raw_history = history_store.get_conversation_messages(conv_id, limit=6)

    # 3. Agent Execution with Tools & Guardrails
    try:
        agent_result = await agent_orchestrator.run(
            session=session,
            user_message=transcript,
            conversation_history=raw_history,
            today_date_str="2026-11-21"
        )
    except Exception as agent_err:
        logger.error(f"Agent Orchestrator Exception: {agent_err}", exc_info=True)
        # Resilient fallback response
        agent_result = {
            "reply_text": "I encountered an issue retrieving that information. Please try again in a moment.",
            "actions_taken": [],
            "pending_action": None,
        }

    reply_text = agent_result.get("reply_text", "")
    actions_taken = agent_result.get("actions_taken", [])

    # 4. Text-to-Speech via Free Neural Edge-TTS (No API key needed)
    audio_base64 = None
    try:
        audio_bytes = await tts_provider.synthesize(reply_text)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    except Exception as tts_err:
        logger.warning(f"TTS Error (Graceful fallback to text transcript): {tts_err}")

    # 5. Persist to Conversation History
    history_store.add_message(conv_id, role="user", content=transcript)
    history_store.add_message(conv_id, role="assistant", content=reply_text, tool_calls=actions_taken)

    return {
        "transcript": transcript,
        "reply_text": reply_text,
        "audio_base64": audio_base64,
        "actions_taken": actions_taken,
        "pending_action": agent_result.get("pending_action"),
        "conversation_id": conv_id,
    }


# --- History Endpoints (Strictly Authenticated) ---
@app.get("/api/v1/history/conversations")
async def list_conversations(session: SessionData = Depends(get_session)):
    if not session.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to view conversation history."
        )
    convs = history_store.get_user_conversations(
        session_id=session.session_id,
        user_id=str(session.user_id)
    )
    return {"conversations": convs}


@app.get("/api/v1/history/conversations/{conv_id}")
async def get_conversation_details(conv_id: str, session: SessionData = Depends(get_session)):
    if not session.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to view conversation details."
        )
    messages = history_store.get_user_conversation_messages(conv_id, user_id=str(session.user_id), limit=50)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Conversation belongs to another user."
        )
    return {"conversation_id": conv_id, "messages": messages}
