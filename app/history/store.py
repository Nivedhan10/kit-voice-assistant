"""Persistent conversation history repository using SQLAlchemy."""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.history.models import Base, DBConversation, DBMessage

logger = logging.getLogger(__name__)

# Setup DB engine
# Works with both SQLite (e.g. sqlite:///./kit_assistant.db) and PostgreSQL (postgresql://...)
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables automatically
Base.metadata.create_all(bind=engine)


class HistoryStore:
    def __init__(self, db_factory=SessionLocal):
        self.db_factory = db_factory

    def get_or_create_active_conversation(
        self, session_id: str, role: str, user_id: Optional[str] = None
    ) -> str:
        with self.db_factory() as db:
            # Query recent active conversation for this session or user
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

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
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

    def get_conversation_messages(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        with self.db_factory() as db:
            query = (
                select(DBMessage)
                .where(DBMessage.conversation_id == conversation_id)
                .order_by(DBMessage.created_at.asc())
            )
            messages = db.execute(query).scalars().all()
            result = []
            for m in messages[-limit:]:
                result.append({
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "created_at": m.created_at.isoformat(),
                })
            return result

    def get_user_conversations(self, session_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.db_factory() as db:
            query = select(DBConversation).order_by(DBConversation.created_at.desc())
            if user_id:
                query = query.where(DBConversation.user_id == str(user_id))
            else:
                query = query.where(DBConversation.session_id == session_id)

            conversations = db.execute(query).scalars().all()
            output = []
            for c in conversations:
                # Count messages
                msg_count = len(c.messages)
                last_msg = c.messages[-1].content if c.messages else ""
                output.append({
                    "id": c.id,
                    "role": c.role,
                    "title": c.title,
                    "message_count": msg_count,
                    "last_message": last_msg[:120],
                    "created_at": c.created_at.isoformat(),
                })
            return output


history_store = HistoryStore()

