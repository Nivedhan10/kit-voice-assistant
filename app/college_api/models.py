"""Pydantic models for Knotopian Institute of Technology (KIT) College System."""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class CollegeUser(BaseModel):
    id: int
    login_id: str
    full_name: str
    role: Literal["student", "teacher"]
    department: Optional[str] = None
    class_id: Optional[int] = None
    class_code: Optional[str] = None
    programme: Optional[str] = None
    year_of_study: Optional[int] = None
    notes: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: CollegeUser


class SubjectAttendance(BaseModel):
    subject_id: int
    subject_code: str
    subject_name: str
    classes_held: int
    classes_attended: int
    classes_od: int
    classes_absent: int
    percentage: float


class AttendanceResponse(BaseModel):
    as_of_date: str
    overall_percentage: float
    total_classes_held: int
    total_classes_attended: int
    subjects: List[SubjectAttendance] = Field(default_factory=list)


class AcademicsResponse(BaseModel):
    user_id: int
    cgpa: float
    standing_arrears: int
    placed_company: Optional[str] = None
    placed_category: Optional[str] = None


class CalendarItem(BaseModel):
    id: int
    date: str
    type: str  # "holiday" | "internal_exam" | "end_semester_exam" | "working_day"
    title: str
    subject_code: Optional[str] = None
    follows_weekday: Optional[int] = None
    status: str = "active"


class TimetableItem(BaseModel):
    id: int
    weekday: int
    period: int
    start_time: str
    end_time: str
    subject_code: str
    subject_name: str


class StudentRequest(BaseModel):
    id: int
    student_id: int
    student_name: str
    class_code: str
    type: str  # "personal_leave" | "medical_leave" | "on_duty"
    from_date: str
    to_date: str
    half_day: Optional[bool] = False
    reason: str
    event_name: Optional[str] = None
    status: str  # "pending" | "approved" | "rejected" | "cancelled"
    decided_by: Optional[int] = None
    decision_note: Optional[str] = None
    created_at: str
    student_notes: Optional[str] = None


class RequestCreatePayload(BaseModel):
    type: Literal["personal_leave", "medical_leave", "on_duty"]
    from_date: str
    to_date: str
    half_day: bool = False
    reason: str
    event_name: Optional[str] = None


class TeacherClass(BaseModel):
    class_id: int
    class_code: str
    department: str
    programme: str
    year: int
    role_type: str  # e.g. "advisor"


class PlacementDrive(BaseModel):
    id: int
    company: str
    category: str
    min_cgpa: float
    allow_standing_arrears: bool
    allowed_departments: List[str] = Field(default_factory=list)
    eligible_years: List[int] = Field(default_factory=list)
    deadline: str
    seats_total: int
    seats_left: int


class Course(BaseModel):
    id: int
    code: str
    name: str
    department: str
    min_12th_percent: float
    annual_fee: float
    hostel_fee: float
    seats: int


class AdmissionApplicationPayload(BaseModel):
    full_name: str
    phone: str
    email: str
    course_code: str
    twelfth_percent: float

