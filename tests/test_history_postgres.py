"""Tests for database URL normalization and conversation history user isolation.
Runs completely offline using SQLite.
"""

import pytest
from app.history.store import normalize_database_url, HistoryStore
from app.history.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_normalize_database_url():
    """Confirms URL normalization handles empty, postgres://, and sslmode parameters."""
    # 1. Empty or None falls back to SQLite
    assert normalize_database_url("") == "sqlite:///./kit_assistant.db"
    assert normalize_database_url("   ") == "sqlite:///./kit_assistant.db"
    assert normalize_database_url(None) == "sqlite:///./kit_assistant.db"

    # 2. postgres:// is normalized to postgresql://
    neon_url = "postgres://user:secret@ep-cool-fog.neon.tech/neondb?sslmode=require"
    expected = "postgresql://user:secret@ep-cool-fog.neon.tech/neondb?sslmode=require"
    assert normalize_database_url(neon_url) == expected

    # 3. postgresql:// is preserved
    standard_pg = "postgresql://user:secret@localhost:5432/mydb"
    assert normalize_database_url(standard_pg) == standard_pg

    # 4. SQLite custom path is preserved
    custom_sqlite = "sqlite:////tmp/test.db"
    assert normalize_database_url(custom_sqlite) == custom_sqlite


def test_history_user_isolation():
    """Confirms conversations are strictly isolated to the authenticated user ID."""
    # Create isolated in-memory test database
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    test_session_factory = sessionmaker(bind=engine)
    store = HistoryStore(db_factory=test_session_factory)

    # User 52 (Arjun) conversation
    arjun_conv = store.get_or_create_active_conversation(
        session_id="sess_arjun_1", role="student", user_id="52"
    )
    store.add_message(arjun_conv, role="user", content="Arjun query about attendance")
    store.add_message(arjun_conv, role="assistant", content="Attendance is 76%")

    # User 53 (Priya) conversation
    priya_conv = store.get_or_create_active_conversation(
        session_id="sess_priya_1", role="student", user_id="53"
    )
    store.add_message(priya_conv, role="user", content="Priya query about leave")
    store.add_message(priya_conv, role="assistant", content="Leave details")

    # Verify user 52 sees only their conversation
    arjun_convs = store.get_user_conversations(session_id="sess_arjun_1", user_id="52")
    assert len(arjun_convs) == 1
    assert arjun_convs[0]["id"] == arjun_conv
    assert arjun_convs[0]["user_id"] == "52"

    # Verify user 53 sees only their conversation
    priya_convs = store.get_user_conversations(session_id="sess_priya_1", user_id="53")
    assert len(priya_convs) == 1
    assert priya_convs[0]["id"] == priya_conv
    assert priya_convs[0]["user_id"] == "53"

    # Verify cross-user access: Priya cannot fetch Arjun's conversation messages
    cross_access = store.get_user_conversation_messages(conversation_id=arjun_conv, user_id="53")
    assert cross_access is None  # Blocked!

    # Arjun fetching Arjun's conversation succeeds
    legit_access = store.get_user_conversation_messages(conversation_id=arjun_conv, user_id="52")
    assert legit_access is not None
    assert len(legit_access) == 2


def test_db_failure_graceful_handling():
    """Confirms DB failures log server-side and don't raise 500 errors."""
    class FailingSessionFactory:
        def __call__(self):
            raise RuntimeError("Simulated connection timeout to cloud DB")

    failing_store = HistoryStore(db_factory=FailingSessionFactory())

    # Should not raise exception, but return fallback ID
    fallback_id = failing_store.get_or_create_active_conversation(
        session_id="sess_1", role="student", user_id="99"
    )
    assert fallback_id.startswith("temp_")

    # Should not raise exception
    msg_id = failing_store.add_message(fallback_id, role="user", content="hello")
    assert msg_id.startswith("err_")

    # Should return empty list, not crash
    convs = failing_store.get_user_conversations(session_id="sess_1", user_id="99")
    assert convs == []

