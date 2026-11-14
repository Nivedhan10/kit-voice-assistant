"""Unit tests for the two-step server-enforced confirmation state machine."""

import pytest
import time
from app.auth.session import SessionData, session_manager
from app.agent.state_machine import is_affirmative, is_negative, process_confirmation_turn


def test_intent_detection():
    assert is_affirmative("Yes, please proceed") is True
    assert is_affirmative("confirm") is True
    assert is_affirmative("go ahead and submit") is True
    assert is_affirmative("sure do it") is True

    assert is_negative("No, stop") is True
    assert is_negative("cancel that") is True
    assert is_negative("don't submit") is True


@pytest.mark.asyncio
async def test_pending_action_cancellation():
    session = session_manager.create_public_session()
    session_manager.set_pending_action(
        session.session_id,
        {
            "tool_name": "submit_admission_application",
            "payload": {"full_name": "Test Student"}
        }
    )

    assert session.pending_action is not None

    # User cancels
    reply, result = await process_confirmation_turn(session, "Cancel this please")
    assert "Cancelled" in reply
    assert result.get("status") == "cancelled"
    # Action must be cleared
    assert session.pending_action is None


@pytest.mark.asyncio
async def test_pending_action_expiry():
    session = session_manager.create_public_session()
    session_manager.set_pending_action(
        session.session_id,
        {
            "tool_name": "apply_leave_or_od",
            "payload": {"reason": "Test"}
        }
    )
    # Manually expire
    session.pending_action["expires_at"] = time.time() - 10

    reply, _ = await process_confirmation_turn(session, "Yes confirm")
    assert "expired" in reply.lower()
    assert session.pending_action is None

