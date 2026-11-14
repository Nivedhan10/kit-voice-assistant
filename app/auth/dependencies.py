"""FastAPI dependencies for session extraction and role enforcement."""

from fastapi import Request, Response, HTTPException, status
from app.auth.session import session_manager, SessionData
from app.config import settings


async def get_session(request: Request, response: Response) -> SessionData:
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    session_id = session_manager.verify_and_get_session_id(cookie_value)
    session = session_manager.get_session(session_id)

    if not session:
        # Create an anonymous public session
        session = session_manager.create_public_session()
        signed_cookie = session_manager._sign(session.session_id)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=signed_cookie,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=False,  # Set to True in production HTTPS
        )

    return session


async def require_authenticated(session: SessionData = None) -> SessionData:
    if not session or not session.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for this service."
        )
    return session


async def require_student(session: SessionData = None) -> SessionData:
    if not session or session.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student privileges required."
        )
    return session


async def require_teacher(session: SessionData = None) -> SessionData:
    if not session or session.role != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher privileges required."
        )
    return session

