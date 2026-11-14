"""Server-enforced confirmation state machine for write actions (Leave, OD, Admissions, Teacher Decisions)."""

import logging
import re
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from app.auth.session import SessionData, session_manager
from app.college_api.client import college_client, CollegeAPIError
from app.college_api.models import (
    AdmissionApplicationPayload,
    RequestCreatePayload,
)

logger = logging.getLogger(__name__)

AFFIRMATIVE_WORDS = {
    "yes", "confirm", "proceed", "go ahead", "do it", "sure", "ok", "okay", "yep",
    "please confirm", "confirmed", "submit", "approve it", "execute"
}

NEGATIVE_WORDS = {
    "no", "cancel", "stop", "abort", "don't", "dont", "never mind", "nope", "discard"
}


def is_affirmative(text: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    words = clean.split()
    if any(w in AFFIRMATIVE_WORDS for w in words):
        return True
    return clean in AFFIRMATIVE_WORDS


def is_negative(text: str) -> bool:
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    words = clean.split()
    if any(w in NEGATIVE_WORDS for w in words):
        return True
    return clean in NEGATIVE_WORDS


async def process_confirmation_turn(
    session: SessionData, user_text: str
) -> Optional[Tuple[str, Dict[str, Any]]]:
    """If there is an active pending action, evaluates user text for confirmation or cancellation.
    Returns (spoken_reply, executed_result_dict) if handled, or None if no pending action or expired.
    """
    pending = session.pending_action
    if not pending:
        return None

    # Check expiration
    if time.time() > pending.get("expires_at", 0):
        session_manager.clear_pending_action(session.session_id)
        return ("Your previous confirmation request has expired. Please repeat your request.", {})

    # Check for cancellation
    if is_negative(user_text):
        session_manager.clear_pending_action(session.session_id)
        action_name = pending.get("tool_name", "Action").replace("_", " ")
        return (f"Cancelled. Your {action_name} has not been submitted.", {"status": "cancelled"})

    # Check for confirmation
    if is_affirmative(user_text):
        tool_name = pending.get("tool_name")
        payload = pending.get("payload", {})
        idempotency_key = pending.get("idempotency_key") or str(uuid.uuid4())
        
        session_manager.clear_pending_action(session.session_id)

        try:
            if tool_name == "apply_leave_or_od":
                req_payload = RequestCreatePayload(**payload)
                result = await college_client.create_request(
                    token=session.college_token, payload=req_payload, idempotency_key=idempotency_key
                )
                req_type_spoken = req_payload.type.replace("_", " ")
                reply = f"Your {req_type_spoken} request from {req_payload.from_date} to {req_payload.to_date} has been successfully submitted."
                return (reply, result.model_dump())

            elif tool_name == "submit_admission_application":
                adm_payload = AdmissionApplicationPayload(**payload)
                result = await college_client.submit_admission_application(
                    payload=adm_payload, idempotency_key=idempotency_key
                )
                reply = f"Thank you {adm_payload.full_name}. Your admission application for {adm_payload.course_code} has been submitted successfully."
                return (reply, result)

            elif tool_name == "cancel_leave_request":
                req_id = payload.get("request_id")
                result = await college_client.cancel_request(token=session.college_token, request_id=req_id)
                reply = f"Request number {req_id} has been cancelled successfully."
                return (reply, result)

            elif tool_name == "decide_student_request":
                req_id = payload.get("request_id")
                decision = payload.get("decision")
                comment_or_reason = payload.get("comment_or_reason", "")

                if decision == "approve":
                    result = await college_client.approve_request(
                        token=session.college_token, request_id=req_id, comment=comment_or_reason
                    )
                    reply = f"Request {req_id} for {result.student_name} has been approved."
                else:
                    result = await college_client.reject_request(
                        token=session.college_token, request_id=req_id, reason=comment_or_reason
                    )
                    reply = f"Request {req_id} for {result.student_name} has been rejected."
                return (reply, result.model_dump())

            elif tool_name == "register_placement_drive":
                drive_id = payload.get("drive_id")
                result = await college_client.register_placement_drive(token=session.college_token, drive_id=drive_id)
                reply = "You have been successfully registered for the placement drive."
                return (reply, result)

            else:
                return ("Unknown pending action. Cancelled.", {})

        except CollegeAPIError as err:
            logger.error(f"College API error executing pending action {tool_name}: {err}")
            return (f"Failed to submit: {err.message}", {"error": str(err)})
        except Exception as e:
            logger.error(f"Unexpected error executing pending action {tool_name}: {e}")
            return ("An unexpected error occurred while executing your request. Please try again.", {"error": str(e)})

    return None
