"""Unit tests for KIT Handbook 2026 & Circular 12/2026 Academic Rules."""

import pytest
from app.rules.leave_validator import validate_leave_request
from app.college_api.models import CalendarItem, StudentRequest


@pytest.fixture
def base_calendar():
    return [
        CalendarItem(id=1, date="2026-11-22", type="holiday", title="Sunday Holiday"),
        CalendarItem(id=2, date="2026-11-23", type="internal_exam", title="DBMS Internal Assessment Exam", subject_code="CS304"),
    ]


@pytest.fixture
def existing_requests():
    return [
        StudentRequest(
            id=10,
            student_id=52,
            student_name="Arjun K",
            class_code="CSE-2A",
            type="personal_leave",
            from_date="2026-11-10",
            to_date="2026-11-10",
            reason="Medical visit",
            status="approved",
            created_at="2026-11-09T00:00:00Z"
        )
    ]


def test_valid_leave_request(base_calendar, existing_requests):
    """A future personal leave on a regular working day with attendance > 75% should be valid."""
    result = validate_leave_request(
        request_type="personal_leave",
        from_date_str="2026-11-25",
        to_date_str="2026-11-25",
        reason="Attending family function",
        as_of_date_str="2026-11-21",
        current_attendance_pct=85.0,
        classes_held=50,
        classes_attended=42,
        calendar_events=base_calendar,
        existing_requests=existing_requests,
    )
    assert result.is_valid is True
    assert result.status == "eligible"
    assert result.reason_code == "APPROVED_FOR_SUBMISSION"


def test_retrospective_personal_leave_blocked(base_calendar, existing_requests):
    """Rule 6.1.1: Personal leave cannot be applied retrospectively."""
    result = validate_leave_request(
        request_type="personal_leave",
        from_date_str="2026-11-15",
        to_date_str="2026-11-15",
        reason="Missed bus",
        as_of_date_str="2026-11-21",
        current_attendance_pct=80.0,
        classes_held=50,
        classes_attended=40,
        calendar_events=base_calendar,
        existing_requests=existing_requests,
    )
    assert result.is_valid is False
    assert result.status == "blocked"
    assert result.reason_code == "RETROSPECTIVE_LEAVE_NOT_ALLOWED"


def test_exam_day_conflict_blocked(base_calendar, existing_requests):
    """Rule 6.1.4: Personal leave cannot be granted on exam days."""
    result = validate_leave_request(
        request_type="personal_leave",
        from_date_str="2026-11-23",  # Exam day in base_calendar fixture
        to_date_str="2026-11-23",
        reason="Family event",
        as_of_date_str="2026-11-21",
        current_attendance_pct=80.0,
        classes_held=50,
        classes_attended=40,
        calendar_events=base_calendar,
        existing_requests=existing_requests,
    )
    assert result.is_valid is False
    assert result.status == "blocked"
    assert result.reason_code == "EXAM_DAY_CONFLICT"
    assert "DBMS Internal Assessment Exam" in result.user_message


def test_duplicate_date_request_blocked(base_calendar):
    """Rule 6.6.3: Duplicate requests for identical dates are prohibited."""
    future_requests = [
        StudentRequest(
            id=10,
            student_id=52,
            student_name="Arjun K",
            class_code="CSE-2A",
            type="personal_leave",
            from_date="2026-11-28",
            to_date="2026-11-28",
            reason="Medical visit",
            status="approved",
            created_at="2026-11-21T00:00:00Z"
        )
    ]
    result = validate_leave_request(
        request_type="personal_leave",
        from_date_str="2026-11-28",  # Already has approved request in future_requests
        to_date_str="2026-11-28",
        reason="Duplicate entry",
        as_of_date_str="2026-11-21",
        current_attendance_pct=80.0,
        classes_held=50,
        classes_attended=40,
        calendar_events=base_calendar,
        existing_requests=future_requests,
    )
    assert result.is_valid is False
    assert result.status == "blocked"
    assert result.reason_code == "DUPLICATE_DATE_REQUEST"


def test_on_duty_missing_event_name_blocked(base_calendar, existing_requests):
    """Rule 6.4.2: Event name is mandatory for on-duty."""
    result = validate_leave_request(
        request_type="on_duty",
        from_date_str="2026-11-28",
        to_date_str="2026-11-28",
        reason="Attending competition",
        as_of_date_str="2026-11-21",
        current_attendance_pct=80.0,
        classes_held=50,
        classes_attended=40,
        calendar_events=base_calendar,
        existing_requests=existing_requests,
        event_name="",  # Empty
    )
    assert result.is_valid is False
    assert result.status == "blocked"
    assert result.reason_code == "MISSING_EVENT_NAME"


def test_on_duty_semester_limit_exceeded(base_calendar):
    """Rule 6.4.5: Max 10 working days on-duty per semester."""
    past_od = [
        StudentRequest(
            id=1,
            student_id=52,
            student_name="Arjun",
            class_code="CSE-2A",
            type="on_duty",
            from_date="2026-09-01",
            to_date="2026-09-09",  # 9 days
            reason="National sports",
            event_name="Athletics",
            status="approved",
            created_at="2026-08-30T00:00:00Z"
        )
    ]
    # Requesting 2 more days -> total 11 > 10
    result = validate_leave_request(
        request_type="on_duty",
        from_date_str="2026-11-28",
        to_date_str="2026-11-29",
        reason="Symposium",
        as_of_date_str="2026-11-21",
        current_attendance_pct=80.0,
        classes_held=50,
        classes_attended=40,
        calendar_events=base_calendar,
        existing_requests=past_od,
        event_name="Tech Fest",
        max_od_days=10,
    )
    assert result.is_valid is False
    assert result.status == "blocked"
    assert result.reason_code == "OD_SEMESTER_LIMIT_EXCEEDED"


def test_attendance_drop_warning(base_calendar, existing_requests):
    """Rule 4.1.1 & 4.2.3: Warning when leave causes attendance to fall below 75%."""
    result = validate_leave_request(
        request_type="personal_leave",
        from_date_str="2026-11-25",
        to_date_str="2026-11-26",  # 2 days = 8 periods missed
        reason="Personal trip",
        as_of_date_str="2026-11-21",
        current_attendance_pct=76.0,  # 38/50 = 76%
        classes_held=50,
        classes_attended=38,
        calendar_events=base_calendar,
        existing_requests=existing_requests,
        min_attendance_threshold=75.0,
    )
    assert result.is_valid is True
    assert result.status == "warning"
    assert result.reason_code == "LEAVE_DROPS_ATTENDANCE_BELOW_THRESHOLD"
    assert result.projected_attendance < 75.0
