"""Persistent conversation history repository using SQLAlchemy.
Supports both SQLite (local/offline test) and Neon PostgreSQL (production).
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.history.models import Base, DBConversation, DBMessage

logger = logging.getLogger(__name__)


def normalize_database_url(url: Optional[str]) -> str:
    """Normalizes database connection string.
    - Empty or None falls back to local SQLite.
    - postgres:// is normalized to postgresql:// (required by SQLAlchemy 2.0).
    - Preserves parameters like sslmode=require for Neon.
    """
    if not url or not url.strip():
        return "sqlite:///./kit_assistant.db"

    clean_url = url.strip()
    if clean_url.startswith("postgres://"):
        clean_url = clean_url.replace("postgres://", "postgresql://", 1)

    return clean_url


# Initialize Engine with Neon-resilient connection pooling
db_url = normalize_database_url(settings.DATABASE_URL)

if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(db_url, connect_args=connect_args, pool_pre_ping=True)
else:
    # PostgreSQL / Neon settings:
    # pool_pre_ping=True tests connections before using (handles Neon scale-to-zero)
    # pool_recycle=300 discards idle connections older than 5 mins
    # connect_timeout=10 prevents hanging on network delays
    connect_args = {"connect_timeout": 10}
    engine = create_engine(
        db_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initializes database schema. Log failure without crashing process."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables verified successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")


# Create tables on import
init_db()


class HistoryStore:
    def __init__(self, db_factory=SessionLocal):
        self.db_factory = db_factory

    def get_or_create_active_conversation(
        self, session_id: str, role: str, user_id: Optional[str] = None
    ) -> str:
        """Retrieves active conversation or creates a new one.
        Guaranteed to not throw 500 on database network errors.
        """
        try:
            with self.db_factory() as db:
                query = select(DBConversation).order_by(DBConversation.created_at.desc())
                if user_id:
                    query = query.where(DBConversation.user_id == str(user_id))
                else:
                    query = query.where(DBConversation.session_id == session_id)

                conv = db.execute(query).scalars().first()
                if conv:
                    return conv.id

                # Create new conversation
                new_conv = DBConversation(
                    user_id=str(user_id) if user_id else None,
                    session_id=session_id,
                    role=role,
                    title=f"KIT {role.capitalize()} Voice Session"
                )
                db.add(new_conv)
                db.commit()
                db.refresh(new_conv)
                return new_conv.id
        except Exception as e:
            logger.error(f"Database error in get_or_create_active_conversation: {e}")
            # Fallback to an ephemeral ID so voice turn continues without failing
            return f"temp_{uuid.uuid4().hex[:12]}"

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Adds a message to the conversation.
        Guaranteed to not throw 500 on database network errors.
        """
        try:
            with self.db_factory() as db:
                msg = DBMessage(
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    tool_calls_json=json.dumps(tool_calls) if tool_calls else None
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)
                return msg.id
        except Exception as e:
            logger.error(f"Database error in add_message: {e}")
            return f"err_{uuid.uuid4().hex[:8]}"

    def get_conversation_messages(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves the latest messages for a conversation."""
        try:
            with self.db_factory() as db:
                query = (
                    select(DBMessage)
                    .where(DBMessage.conversation_id == conversation_id)
                    .order_by(DBMessage.created_at.asc())
                )
                messages = db.execute(query).scalars().all()
                result = []
                for m in messages[-limit:]:
                    tool_calls_data = None
                    if m.tool_calls_json:
                        try:
                            tool_calls_data = json.loads(m.tool_calls_json)
                        except Exception:
                            pass
                    result.append({
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                        "tool_calls": tool_calls_data,
                        "created_at": m.created_at.isoformat(),
                    })
                return result
        except Exception as e:
            logger.error(f"Database error in get_conversation_messages: {e}")
            return []

    def get_user_conversation_messages(self, conversation_id: str, user_id: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
        """Retrieves messages for a conversation only if it belongs to the requesting user."""
        try:
            with self.db_factory() as db:
                conv = db.execute(select(DBConversation).where(DBConversation.id == conversation_id)).scalars().first()
                if not conv:
                    return None
                # Strict user isolation
                if conv.user_id != str(user_id):
                    return None
                return self.get_conversation_messages(conversation_id, limit=limit)
        except Exception as e:
            logger.error(f"Database error in get_user_conversation_messages: {e}")
            return None

    def get_user_conversations(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves list of conversations strictly for the authenticated user."""
        try:
            with self.db_factory() as db:
                if not user_id:
                    return []
                query = (
                    select(DBConversation)
                    .where(DBConversation.user_id == str(user_id))
                    .order_by(DBConversation.created_at.desc())
                )

                conversations = db.execute(query).scalars().all()
                output = []
                for c in conversations:
                    msg_count = len(c.messages)
                    last_msg = c.messages[-1].content if c.messages else ""
                    output.append({
                        "id": c.id,
                        "role": c.role,
                        "title": c.title,
                        "user_id": c.user_id,
                        "message_count": msg_count,
                        "last_message": last_msg[:120],
                        "created_at": c.created_at.isoformat(),
                    })
                return output
        except Exception as e:
            logger.error(f"Database error in get_user_conversations: {e}")
            return []


history_store = HistoryStore()
