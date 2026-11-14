"""SQLAlchemy database models for persistent conversation history."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utc_now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class DBConversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "public", "student", "teacher"
    title: Mapped[str] = mapped_column(String(255), default="Voice Conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    messages: Mapped[List["DBMessage"]] = relationship("DBMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="DBMessage.created_at")


class DBMessage(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "user", "assistant", "tool"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utc_now)

    conversation: Mapped["DBConversation"] = relationship("DBConversation", back_populates="messages")

