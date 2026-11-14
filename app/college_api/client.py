"""Async client for interacting with the Knotopian Institute of Technology (KIT) College System API."""

import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import settings
from app.college_api.models import (
    AdmissionApplicationPayload,
    AttendanceResponse,
    AcademicsResponse,
    CalendarItem,
    Course,
    LoginResponse,
    PlacementDrive,
    RequestCreatePayload,
    StudentRequest,
    TeacherClass,
    TimetableItem,
    CollegeUser,
)

logger = logging.getLogger(__name__)


class CollegeAPIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, field: Optional[str] = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field
        super().__init__(f"[{status_code}] {code}: {message} (field={field})")


class CollegeClient:
    def __init__(self, base_url: Optional[str] = None, participant_key: Optional[str] = None):
        self.base_url = (base_url or settings.COLLEGE_API_BASE_URL).rstrip("/")
        self.participant_key = participant_key or settings.COLLEGE_API_KEY
        self.timeout = httpx.Timeout(10.0, connect=5.0)

    def _headers(self, token: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "X-Participant-Key": self.participant_key,
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        token: Optional[str] = None,
        json_data: Optional[Any] = None,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers(token, idempotency_key)
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.request(method, url, headers=headers, json=json_data)
            except httpx.RequestError as exc:
                logger.error(f"HTTP request error to {url}: {exc}")
                raise CollegeAPIError(503, "NETWORK_ERROR", f"Could not connect to College System: {str(exc)}")

            if resp.status_code >= 400:
                try:
                    err_json = resp.json()
                    err = err_json.get("error", {})
                    code = err.get("code", "API_ERROR")
                    message = err.get("message", resp.text)
                    field = err.get("field")
                except Exception:
                    code = "HTTP_ERROR"
                    message = resp.text
                    field = None
                logger.warning(f"College API returned error {resp.status_code} for {path}: {message}")
                raise CollegeAPIError(resp.status_code, code, message, field)

            if resp.status_code == 204 or not resp.content:
                return None
            return resp.json()

    # --- Authentication ---
    async def login(self, login_id: str, password: str) -> LoginResponse:
        data = await self._request("POST", "/v1/auth/login", json_data={"login_id": login_id, "password": password})
        return LoginResponse(**data)

    # --- Student Details ---
    async def get_me(self, token: str) -> CollegeUser:
        data = await self._request("GET", "/v1/me", token=token)
        return CollegeUser(**data)

    async def get_attendance(self, token: str) -> AttendanceResponse:
        data = await self._request("GET", "/v1/me/attendance", token=token)
        return AttendanceResponse(**data)

    async def get_academics(self, token: str) -> AcademicsResponse:
        data = await self._request("GET", "/v1/me/academics", token=token)
        return AcademicsResponse(**data)

    async def get_timetable(self, token: str) -> List[TimetableItem]:
        data = await self._request("GET", "/v1/me/timetable", token=token)
        return [TimetableItem(**item) for item in data]

    async def get_calendar(self, token: Optional[str] = None) -> List[CalendarItem]:
        data = await self._request("GET", "/v1/calendar", token=token)
        return [CalendarItem(**item) for item in data]

    async def get_today(self) -> Dict[str, Any]:
        return await self._request("GET", "/v1/today")

    # --- Student Leave & On-Duty Requests ---
    async def get_my_requests(self, token: str) -> List[StudentRequest]:
        data = await self._request("GET", "/v1/me/requests", token=token)
        return [StudentRequest(**item) for item in data]

    async def create_request(
        self, token: str, payload: RequestCreatePayload, idempotency_key: Optional[str] = None
    ) -> StudentRequest:
        data = await self._request(
            "POST", "/v1/me/requests", token=token, json_data=payload.model_dump(exclude_none=True), idempotency_key=idempotency_key
        )
        return StudentRequest(**data)

    async def cancel_request(self, token: str, request_id: int) -> Dict[str, Any]:
        return await self._request("POST", f"/v1/me/requests/{request_id}/cancel", token=token)

    # --- Teacher Endpoints ---
    async def get_teacher_classes(self, token: str) -> List[TeacherClass]:
        data = await self._request("GET", "/v1/teacher/classes", token=token)
        return [TeacherClass(**item) for item in data]

    async def get_teacher_requests(self, token: str) -> List[StudentRequest]:
        data = await self._request("GET", "/v1/teacher/requests", token=token)
        return [StudentRequest(**item) for item in data]

    async def approve_request(self, token: str, request_id: int, comment: Optional[str] = None) -> StudentRequest:
        payload = {"comment": comment} if comment else {}
        data = await self._request("POST", f"/v1/teacher/requests/{request_id}/approve", token=token, json_data=payload)
        return StudentRequest(**data)

    async def reject_request(self, token: str, request_id: int, reason: str) -> StudentRequest:
        payload = {"reason": reason}
        data = await self._request("POST", f"/v1/teacher/requests/{request_id}/reject", token=token, json_data=payload)
        return StudentRequest(**data)

    # --- Public & Academic Endpoints ---
    async def get_college_info(self) -> Dict[str, Any]:
        return await self._request("GET", "/v1/college")

    async def get_courses(self) -> List[Course]:
        data = await self._request("GET", "/v1/courses")
        return [Course(**item) for item in data]

    async def submit_admission_application(
        self, payload: AdmissionApplicationPayload, idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        return await self._request(
            "POST", "/v1/admissions/applications", json_data=payload.model_dump(), idempotency_key=idempotency_key
        )

    # --- Placements ---
    async def get_placement_drives(self, token: Optional[str] = None) -> List[PlacementDrive]:
        data = await self._request("GET", "/v1/placements/drives", token=token)
        return [PlacementDrive(**item) for item in data]

    async def register_placement_drive(self, token: str, drive_id: int) -> Dict[str, Any]:
        return await self._request("POST", f"/v1/placements/drives/{drive_id}/register", token=token)


college_client = CollegeClient()

