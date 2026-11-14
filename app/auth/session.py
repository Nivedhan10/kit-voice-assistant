"""Server-side session management with signed cookies and strict role-based access control."""

import hmac
import hashlib
import time
import uuid
from typing import Dict, Optional, Literal, Any
from pydantic import BaseModel, Field

from app.config import settings


class SessionData(BaseModel):
    session_id: str
    user_id: Optional[int] = None
    login_id: Optional[str] = None
    full_name: Optional[str] = None
    role: Literal["public", "student", "teacher"] = "public"
    department: Optional[str] = None
    class_id: Optional[int] = None
    class_code: Optional[str] = None
    programme: Optional[str] = None
    year_of_study: Optional[int] = None
    notes: Optional[str] = None
    college_token: Optional[str] = None  # Stored server-side only! Never sent to client or LLM
    pending_action: Optional[Dict[str, Any]] = None  # Two-step confirmation state
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + settings.SESSION_MAX_AGE_SECONDS)

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def is_authenticated(self) -> bool:
        return self.role in ("student", "teacher") and self.college_token is not None


class SessionManager:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode("utf-8")
        self._sessions: Dict[str, SessionData] = {}

    def _sign(self, session_id: str) -> str:
        sig = hmac.new(self.secret_key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{session_id}.{sig}"

    def verify_and_get_session_id(self, signed_cookie: Optional[str]) -> Optional[str]:
        if not signed_cookie or "." not in signed_cookie:
            return None
        parts = signed_cookie.split(".", 1)
        if len(parts) != 2:
            return None
        session_id, sig = parts
        expected_sig = hmac.new(self.secret_key, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return session_id
        return None

    def create_public_session(self) -> SessionData:
        session_id = str(uuid.uuid4())
        session = SessionData(
            session_id=session_id,
            role="public",
            expires_at=time.time() + settings.SESSION_MAX_AGE_SECONDS
        )
        self._sessions[session_id] = session
        return session

    def create_authenticated_session(
        self,
        college_token: str,
        user_info: Dict[str, Any],
    ) -> SessionData:
        session_id = str(uuid.uuid4())
        session = SessionData(
            session_id=session_id,
            user_id=user_info.get("id"),
            login_id=user_info.get("login_id"),
            full_name=user_info.get("full_name"),
            role=user_info.get("role", "student"),
            department=user_info.get("department"),
            class_id=user_info.get("class_id"),
            class_code=user_info.get("class_code"),
            programme=user_info.get("programme"),
            year_of_study=user_info.get("year_of_study"),
            notes=user_info.get("notes"),
            college_token=college_token,
            expires_at=time.time() + settings.SESSION_MAX_AGE_SECONDS
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: Optional[str]) -> Optional[SessionData]:
        if not session_id or session_id not in self._sessions:
            return None
        session = self._sessions[session_id]
        if session.is_expired():
            del self._sessions[session_id]
            return None
        return session

    def delete_session(self, session_id: Optional[str]) -> None:
        if session_id and session_id in self._sessions:
            del self._sessions[session_id]

    def set_pending_action(self, session_id: str, action_data: Dict[str, Any]) -> None:
        session = self.get_session(session_id)
        if session:
            action_data["created_at"] = time.time()
            action_data["expires_at"] = time.time() + settings.CONFIRMATION_TIMEOUT_SECONDS
            session.pending_action = action_data

    def clear_pending_action(self, session_id: str) -> None:
        session = self.get_session(session_id)
        if session:
            session.pending_action = None


session_manager = SessionManager(settings.SESSION_SECRET_KEY)

