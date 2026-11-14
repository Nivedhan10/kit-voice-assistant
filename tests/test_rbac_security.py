"""Security and Role-Based Access Control (RBAC) tests."""

import pytest
from app.agent.registry import get_tools_for_role, get_tool_definition
from app.auth.session import SessionData
from app.agent.orchestrator import AgentOrchestrator
from app.kb.search import search_college_handbook, search_lesson_notes, search_admission_brochure
from app.providers.base import LLMProvider, LLMResponse


class DummyLLM(LLMProvider):
    async def chat(self, messages, tools=None, tool_choice="auto"):
        return LLMResponse(content="Dummy response")


def test_public_role_tools_isolated():
    """Public role must only see public admission and course tools."""
    tools = get_tools_for_role("public")
    tool_names = {t["function"]["name"] for t in tools}

    assert "search_admission_brochure" in tool_names
    assert "submit_admission_application" in tool_names
    assert "get_available_courses" in tool_names

    # MUST NOT CONTAIN any student or teacher tools
    assert "get_student_attendance" not in tool_names
    assert "apply_leave_or_od" not in tool_names
    assert "get_academic_schedule" not in tool_names
    assert "search_college_handbook" not in tool_names
    assert "search_lesson_notes" not in tool_names
    assert "get_teacher_classes" not in tool_names
    assert "decide_student_request" not in tool_names


def test_student_role_cannot_see_teacher_tools():
    """Student role must not receive teacher approval tools."""
    tools = get_tools_for_role("student")
    tool_names = {t["function"]["name"] for t in tools}

    assert "get_student_attendance" in tool_names
    assert "apply_leave_or_od" in tool_names
    assert "search_lesson_notes" in tool_names

    # Denied teacher tools
    assert "get_teacher_classes" not in tool_names
    assert "get_assigned_pending_requests" not in tool_names
    assert "decide_student_request" not in tool_names


@pytest.mark.asyncio
async def test_unauthorized_tool_execution_blocked():
    """Direct invocation of a student tool by a public session is blocked by the orchestrator."""
    orchestrator = AgentOrchestrator(llm_provider=DummyLLM())
    public_session = SessionData(session_id="anon-123", role="public")

    result, needs_confirm, _ = await orchestrator.execute_tool(
        tool_name="get_student_attendance",
        arguments={},
        session=public_session
    )

    assert "error" in result
    assert "Permission denied" in result["error"]


def test_knowledge_base_role_enforcement():
    """Handbook and lesson notes are protected by role boundaries."""
    # Brochure is accessible to public
    brochure_res = search_admission_brochure("courses")
    assert len(brochure_res) > 0

    # Handbook is blocked for public
    with pytest.raises(PermissionError):
        search_college_handbook("attendance rule", role="public")

    # Lesson notes are blocked for public and teacher
    with pytest.raises(PermissionError):
        search_lesson_notes("DBMS", "What is 3NF?", role="public")

    with pytest.raises(PermissionError):
        search_lesson_notes("DBMS", "What is 3NF?", role="teacher")


def test_tool_schemas_do_not_contain_user_identity_parameters():
    """Identity parameter security check: Tools must never accept student_id or user_id."""
    tools = get_tools_for_role("student")
    for t in tools:
        params = t["function"]["parameters"].get("properties", {})
        assert "user_id" not in params, f"Security risk: {t['function']['name']} exposes user_id parameter"
        assert "student_id" not in params, f"Security risk: {t['function']['name']} exposes student_id parameter"


def test_health_endpoints():
    """Both /health and /api/v1/health must return 200 without network dependencies."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"

    r2 = client.get("/api/v1/health")
    assert r2.status_code == 200
    assert r2.json()["status"] == "healthy"


def test_history_endpoint_unauthenticated_blocked():
    """Unauthenticated access to conversation history must be rejected with 401."""
    from starlette.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/api/v1/history/conversations")
    assert res.status_code == 401
    assert "Authentication required" in res.json()["detail"]

