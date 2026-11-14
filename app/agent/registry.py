"""Single source of truth for all tools, role permissions, parameters, and confirmation flags."""

from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel


class ToolDefinition(BaseModel):
    name: str
    description: str
    allowed_roles: List[str]
    parameters: Dict[str, Any]
    needs_confirmation: bool = False
    college_endpoint: str


# Global Registry List
TOOL_REGISTRY: List[ToolDefinition] = [
    # 1. PUBLIC ADMISSIONS & COURSES (Accessible: public, student, teacher)
    ToolDefinition(
        name="search_admission_brochure",
        description="Search admission criteria, eligibility, tuition fees, seat intake, and application procedure.",
        allowed_roles=["public", "student", "teacher"],
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The specific admission, fees, or program question to search."
                }
            },
            "required": ["query"]
        },
        needs_confirmation=False,
        college_endpoint="Internal KB (Admissions Brochure 2026)"
    ),
    ToolDefinition(
        name="get_available_courses",
        description="Retrieve active academic courses, departments, seat matrix, and annual fees.",
        allowed_roles=["public", "student", "teacher"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/courses"
    ),
    ToolDefinition(
        name="get_college_overview",
        description="Get official institute overview, accreditation, campus address, and admissions contact numbers.",
        allowed_roles=["public", "student", "teacher"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/college"
    ),
    ToolDefinition(
        name="submit_admission_application",
        description="Submit prospective applicant details for admission into an undergraduate engineering course.",
        allowed_roles=["public"],
        parameters={
            "type": "object",
            "properties": {
                "full_name": {"type": "string", "description": "Candidate's full legal name."},
                "phone": {"type": "string", "description": "Contact phone number (e.g. +91 9876543210)."},
                "email": {"type": "string", "description": "Candidate's email address."},
                "course_code": {
                    "type": "string",
                    "description": "Course code applied for, e.g. BTECH-CSE, BTECH-ECE, BTECH-MECH."
                },
                "twelfth_percent": {
                    "type": "number",
                    "description": "12th Standard board marks percentage (e.g. 88.5)."
                }
            },
            "required": ["full_name", "phone", "email", "course_code", "twelfth_percent"]
        },
        needs_confirmation=True,
        college_endpoint="POST /v1/admissions/applications"
    ),

    # 2. AUTHENTICATED STUDENT TOOLS (Accessible: student ONLY)
    ToolDefinition(
        name="get_student_attendance",
        description="Get the authenticated student's overall attendance percentage and per-subject attendance breakdown.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/me/attendance"
    ),
    ToolDefinition(
        name="get_student_academics",
        description="Retrieve the authenticated student's academic standing, including cumulative CGPA, standing arrears, and placement status.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/me/academics"
    ),
    ToolDefinition(
        name="get_academic_schedule",
        description="Get academic schedule, including timetable, active semester calendar, holidays, and examination dates.",
        allowed_roles=["student", "teacher"],
        parameters={
            "type": "object",
            "properties": {
                "schedule_type": {
                    "type": "string",
                    "enum": ["timetable", "calendar", "exams", "holidays"],
                    "description": "Type of schedule information requested."
                }
            },
            "required": ["schedule_type"]
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/me/timetable | GET /v1/calendar"
    ),
    ToolDefinition(
        name="apply_leave_or_od",
        description="Apply for Personal Leave, Medical Leave, or On-Duty (OD). Automatically checked against Handbook rules.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {
                "request_type": {
                    "type": "string",
                    "enum": ["personal_leave", "medical_leave", "on_duty"],
                    "description": "Type of request."
                },
                "from_date": {"type": "string", "description": "Start date in YYYY-MM-DD format."},
                "to_date": {"type": "string", "description": "End date in YYYY-MM-DD format."},
                "reason": {"type": "string", "description": "Reason for leave or on-duty."},
                "event_name": {
                    "type": "string",
                    "description": "Mandatory event/symposium/competition name if request_type is on_duty."
                },
                "half_day": {"type": "boolean", "description": "Whether request is for half a day. Default false."}
            },
            "required": ["request_type", "from_date", "to_date", "reason"]
        },
        needs_confirmation=True,
        college_endpoint="POST /v1/me/requests"
    ),
    ToolDefinition(
        name="get_my_requests",
        description="View status of past and active leave and on-duty requests submitted by the student.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/me/requests"
    ),
    ToolDefinition(
        name="cancel_leave_request",
        description="Cancel a pending or upcoming approved leave request before its start date.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {
                "request_id": {"type": "integer", "description": "The ID of the request to cancel."}
            },
            "required": ["request_id"]
        },
        needs_confirmation=True,
        college_endpoint="POST /v1/me/requests/{id}/cancel"
    ),
    ToolDefinition(
        name="search_college_handbook",
        description="Search institutional regulations from Student Handbook 2026 and Circular 12/2026.",
        allowed_roles=["student", "teacher"],
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The regulation or rule topic to search."}
            },
            "required": ["query"]
        },
        needs_confirmation=False,
        college_endpoint="Internal KB (Handbook 2026 & Circular 12/2026)"
    ),
    ToolDefinition(
        name="search_lesson_notes",
        description="Ask subject-specific doubts and queries based on lecture notes (e.g. DBMS CS304).",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Course code or subject title (e.g. CS304, DBMS)."},
                "question": {"type": "string", "description": "The specific conceptual question or doubt."}
            },
            "required": ["subject", "question"]
        },
        needs_confirmation=False,
        college_endpoint="Internal KB (DBMS CS304 Notes)"
    ),
    ToolDefinition(
        name="get_placement_drives",
        description="List active campus placement recruitment drives, minimum CGPA eligibility, and remaining seats.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/placements/drives"
    ),
    ToolDefinition(
        name="register_placement_drive",
        description="Register for a corporate placement recruitment drive. Validates student eligibility (CGPA, Year, Arrears).",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer", "description": "The ID of the placement drive."}
            },
            "required": ["drive_id"]
        },
        needs_confirmation=True,
        college_endpoint="POST /v1/placements/drives/{id}/register"
    ),
    ToolDefinition(
        name="get_my_placement_registrations",
        description="List placement recruitment drives the authenticated student has already registered for.",
        allowed_roles=["student"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/me/placements"
    ),

    # 3. AUTHENTICATED TEACHER TOOLS (Accessible: teacher ONLY)
    ToolDefinition(
        name="get_teacher_classes",
        description="List classes and student groups assigned to this teacher / advisor.",
        allowed_roles=["teacher"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/teacher/classes"
    ),
    ToolDefinition(
        name="get_class_attendance_sheet",
        description="Retrieve class-wide student attendance sheet and percentages for an authorized class section.",
        allowed_roles=["teacher"],
        parameters={
            "type": "object",
            "properties": {
                "class_id": {"type": "integer", "description": "The class ID to retrieve attendance for."}
            },
            "required": ["class_id"]
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/teacher/classes/{class_id}/attendance"
    ),
    ToolDefinition(
        name="get_assigned_pending_requests",
        description="List pending student leave and on-duty requests strictly belonging to this teacher's advised classes.",
        allowed_roles=["teacher"],
        parameters={
            "type": "object",
            "properties": {}
        },
        needs_confirmation=False,
        college_endpoint="GET /v1/teacher/requests"
    ),
    ToolDefinition(
        name="decide_student_request",
        description="Approve or reject a pending leave or on-duty request from an authorized student.",
        allowed_roles=["teacher"],
        parameters={
            "type": "object",
            "properties": {
                "request_id": {"type": "integer", "description": "The ID of the student request."},
                "decision": {
                    "type": "string",
                    "enum": ["approve", "reject"],
                    "description": "Decision outcome."
                },
                "comment_or_reason": {
                    "type": "string",
                    "description": "Optional approval comment, or mandatory rejection reason."
                }
            },
            "required": ["request_id", "decision", "comment_or_reason"]
        },
        needs_confirmation=True,
        college_endpoint="POST /v1/teacher/requests/{id}/approve | reject"
    ),
]


def get_tools_for_role(role: str) -> List[Dict[str, Any]]:
    """Returns OpenAI-compatible tool specifications filtered strictly by role."""
    tools: List[Dict[str, Any]] = []
    for tool in TOOL_REGISTRY:
        if role in tool.allowed_roles:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            })
    return tools


def get_tool_definition(name: str) -> Optional[ToolDefinition]:
    for tool in TOOL_REGISTRY:
        if tool.name == name:
            return tool
    return None


def generate_markdown_permissions_table() -> str:
    """Generates a Markdown table of all registered tools and their RBAC permissions for README."""
    lines = [
        "| Tool Name | Allowed Roles | Needs Confirmation? | Backend / College Endpoint |",
        "|---|---|---|---|"
    ]
    for t in TOOL_REGISTRY:
        roles_str = ", ".join(f"`{r}`" for r in t.allowed_roles)
        confirm_str = "**Yes**" if t.needs_confirmation else "No"
        lines.append(f"| `{t.name}` | {roles_str} | {confirm_str} | `{t.college_endpoint}` |")
    return "\n".join(lines)

