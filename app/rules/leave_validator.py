"""Pure business rule validation for leave and on-duty requests according to KIT Handbook 2026 & Circular 12/2026."""

from datetime import date, datetime
from typing import List, Optional, Literal
from pydantic import BaseModel

from app.config import settings
from app.college_api.models import CalendarItem, StudentRequest


class ValidationResult(BaseModel):
    is_valid: bool
    status: Literal["eligible", "blocked", "warning"]
    reason_code: str
    user_message: str
    rule_reference: str
    projected_attendance: Optional[float] = None


def parse_date(date_str: str) -> date:
    """Parses date string YYYY-MM-DD into a date object."""
    if isinstance(date_str, date):
        return date_str
    return datetime.strptime(date_str.strip()[:10], "%Y-%m-%d").date()


def validate_leave_request(
    request_type: Literal["personal_leave", "medical_leave", "on_duty"],
    from_date_str: str,
    to_date_str: str,
    reason: str,
    as_of_date_str: str,
    current_attendance_pct: float,
    classes_held: int,
    classes_attended: int,
    calendar_events: List[CalendarItem],
    existing_requests: List[StudentRequest],
    event_name: Optional[str] = None,
    half_day: bool = False,
    min_attendance_threshold: Optional[float] = None,
    max_od_days: Optional[int] = None,
) -> ValidationResult:
    """Pure validation function for student leave and on-duty requests.
    
    References:
    - Rule 6.1.1: Advance application notice (>= 24 hours). Retrospective personal leave blocked.
    - Rule 6.1.4: No personal leave on exam days.
    - Rule 6.4.2: Event name required for On-Duty.
    - Rule 6.4.5: Maximum 10 working days On-Duty per semester.
    - Rule 6.4.7: No OD during Internal Assessment without special approval.
    - Rule 4.1.1: Minimum 75% attendance requirement.
    - Rule 6.6.3: Duplicate requests for identical dates prohibited.
    - Circular 12/2026: Proof submission required within 3 working days.
    """
    min_threshold = min_attendance_threshold if min_attendance_threshold is not None else settings.MIN_ATTENDANCE_PERCENT
    max_od = max_od_days if max_od_days is not None else settings.MAX_OD_DAYS_PER_SEMESTER

    # 1. Date Format & Range Validity
    try:
        from_date = parse_date(from_date_str)
        to_date = parse_date(to_date_str)
        as_of_date = parse_date(as_of_date_str)
    except Exception as e:
        return ValidationResult(
            is_valid=False,
            status="blocked",
            reason_code="INVALID_DATE_FORMAT",
            user_message="The dates provided are not valid. Please provide dates in YYYY-MM-DD format.",
            rule_reference="Rule 6.1.1"
        )

    if from_date > to_date:
        return ValidationResult(
            is_valid=False,
            status="blocked",
            reason_code="INVALID_DATE_RANGE",
            user_message="The leave start date cannot be later than the end date.",
            rule_reference="Rule 6.1.1"
        )

    # 2. Advance Notice & Retrospective Check (Rule 6.1.1)
    # Personal leave must be applied before start date.
    if request_type == "personal_leave" and from_date < as_of_date:
        return ValidationResult(
            is_valid=False,
            status="blocked",
            reason_code="RETROSPECTIVE_LEAVE_NOT_ALLOWED",
            user_message="Personal leave cannot be applied retrospectively. Only medical leave can be submitted after absence.",
            rule_reference="Handbook 2026, Rule 6.1.1 & Rule 6.1.2"
        )

    # 3. Duplicate Date Request Check (Rule 6.6.3)
    for req in existing_requests:
        if req.status in ("pending", "approved"):
            req_from = parse_date(req.from_date)
            req_to = parse_date(req.to_date)
            # Check overlap
            if not (to_date < req_from or from_date > req_to):
                return ValidationResult(
                    is_valid=False,
                    status="blocked",
                    reason_code="DUPLICATE_DATE_REQUEST",
                    user_message=f"You already have a {req.status} {req.type.replace('_', ' ')} covering {req.from_date} to {req.to_date}.",
                    rule_reference="Handbook 2026, Rule 6.6.3"
                )

    # 4. Exam Conflict Check (Rule 6.1.4 & Rule 6.4.7)
    exam_conflicts = []
    for event in calendar_events:
        if event.status == "active" and event.type in ("internal_exam", "end_semester_exam"):
            event_date = parse_date(event.date)
            if from_date <= event_date <= to_date:
                exam_conflicts.append(f"{event.title} on {event.date}")

    if exam_conflicts:
        if request_type == "personal_leave":
            return ValidationResult(
                is_valid=False,
                status="blocked",
                reason_code="EXAM_DAY_CONFLICT",
                user_message=f"Leave cannot be granted on exam days: {', '.join(exam_conflicts)}.",
                rule_reference="Handbook 2026, Rule 6.1.4"
            )
        elif request_type == "on_duty":
            # Rule 6.4.7
            return ValidationResult(
                is_valid=False,
                status="blocked",
                reason_code="EXAM_DAY_CONFLICT_OD",
                user_message=f"On-Duty is not permitted during exams ({', '.join(exam_conflicts)}) unless specifically approved by the Principal.",
                rule_reference="Handbook 2026, Rule 6.4.7"
            )

    # 5. On-Duty Specific Rules (Rule 6.4.2, Rule 6.4.5, Circular 12/2026)
    if request_type == "on_duty":
        if not event_name or not event_name.strip():
            return ValidationResult(
                is_valid=False,
                status="blocked",
                reason_code="MISSING_EVENT_NAME",
                user_message="An event name is required for all On-Duty requests.",
                rule_reference="Handbook 2026, Rule 6.4.2"
            )

        # Count total OD days taken this semester
        total_od_days = 0
        for req in existing_requests:
            if req.type == "on_duty" and req.status in ("approved", "pending"):
                od_from = parse_date(req.from_date)
                od_to = parse_date(req.to_date)
                total_od_days += (od_to - od_from).days + 1

        requested_days = (to_date - from_date).days + 1
        if (total_od_days + requested_days) > max_od:
            return ValidationResult(
                is_valid=False,
                status="blocked",
                reason_code="OD_SEMESTER_LIMIT_EXCEEDED",
                user_message=f"Requested {requested_days} OD days exceeds the semester maximum of {max_od} days (already used: {total_od_days} days).",
                rule_reference="Handbook 2026, Rule 6.4.5"
            )

    # 6. Attendance Impact Estimation (Rule 4.1.1 & Rule 4.2.3)
    # Estimate periods missed based on days (assume average 4 periods/day unless half-day)
    requested_days = (to_date - from_date).days + 1
    missed_periods = 2 if half_day else (requested_days * 4)
    
    projected_held = classes_held + missed_periods
    projected_attended = classes_attended  # Stays same for personal leave (Rule 4.2.3)
    if request_type == "on_duty":
        # Approved OD counts as attended (Rule 4.2.1, Rule 6.4.6)
        projected_attended += missed_periods

    projected_pct = round((projected_attended / projected_held) * 100, 1) if projected_held > 0 else 100.0

    # If personal leave drops attendance below 75%
    if request_type == "personal_leave":
        if current_attendance_pct < min_threshold:
            return ValidationResult(
                is_valid=True,
                status="warning",
                reason_code="ATTENDANCE_CURRENTLY_BELOW_THRESHOLD",
                user_message=f"Warning: Your attendance is currently {current_attendance_pct}%, which is below the required {min_threshold}%. Taking this leave will reduce it further to ~{projected_pct}%.",
                rule_reference="Handbook 2026, Rule 4.1.1 & Rule 4.1.4",
                projected_attendance=projected_pct
            )
        elif projected_pct < min_threshold:
            return ValidationResult(
                is_valid=True,
                status="warning",
                reason_code="LEAVE_DROPS_ATTENDANCE_BELOW_THRESHOLD",
                user_message=f"Caution: Taking this leave will drop your attendance from {current_attendance_pct}% to ~{projected_pct}%, which is below the required {min_threshold}%.",
                rule_reference="Handbook 2026, Rule 4.1.1 & Rule 4.2.3",
                projected_attendance=projected_pct
            )

    # All checks passed
    od_reminder = " Remember to submit event proof within 3 working days." if request_type == "on_duty" else ""
    return ValidationResult(
        is_valid=True,
        status="eligible",
        reason_code="APPROVED_FOR_SUBMISSION",
        user_message=f"Request details are valid and meet academic regulations.{od_reminder}",
        rule_reference="Handbook 2026, Chapter 6 & Circular 12/2026",
        projected_attendance=projected_pct
    )

