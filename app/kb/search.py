"""Scoped knowledge retrieval with strict role boundaries for Brochure, Handbook, and Lesson Notes."""

import os
import re
from typing import List, Dict, Tuple


def _read_file_safe(path: str) -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return ""


# Pre-load knowledge files
BROCHURE_TEXT = _read_file_safe("data/knowledge/admissions_brochure.txt")
HANDBOOK_TEXT = _read_file_safe("data/knowledge/handbook_rules.txt")
CIRCULAR_TEXT = _read_file_safe("data/knowledge/circular_12_2026.txt")
DBMS_NOTES_TEXT = _read_file_safe("data/knowledge/dbms_lesson_notes.txt")


def _keyword_search(text: str, query: str, max_snippets: int = 3, window_chars: int = 400) -> str:
    """Finds top relevant paragraphs or snippets containing query words."""
    if not text:
        return "No documentation available."

    words = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 2]
    if not words:
        return text[:1000]

    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    scored: List[Tuple[int, str]] = []

    for para in paragraphs:
        p_lower = para.lower()
        score = sum(p_lower.count(w) * (3 if len(w) > 4 else 1) for w in words)
        if score > 0:
            scored.append((score, para))

    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        top_paras = [item[1] for item in scored[:max_snippets]]
        return "\n\n---\n\n".join(top_paras)

    # Fallback to first page
    return text[:800]


def search_admission_brochure(query: str) -> str:
    """Answers admission, fees, courses, eligibility and application procedure questions.
    Accessible by: Public, Student, Teacher.
    """
    results = _keyword_search(BROCHURE_TEXT, query, max_snippets=4)
    return f"Admissions Brochure Information:\n{results}"


def search_college_handbook(query: str, role: str) -> str:
    """Answers institutional rules on attendance, exams, leaves, conduct, and fees.
    Accessible by: Student, Teacher ONLY.
    """
    if role not in ("student", "teacher"):
        raise PermissionError("Access denied: College handbook is only accessible to authenticated students and teachers.")

    # Combine handbook with Circular 12/2026
    combined = f"LATEST ACTIVE CIRCULARS:\n{CIRCULAR_TEXT}\n\nACADEMIC REGULATIONS AND HANDBOOK:\n{HANDBOOK_TEXT}"
    results = _keyword_search(combined, query, max_snippets=4)
    return f"Handbook & Regulations Reference:\n{results}"


def search_lesson_notes(subject: str, query: str, role: str) -> str:
    """Answers academic questions and doubts from subject lesson notes.
    Accessible by: Student ONLY.
    """
    if role != "student":
        raise PermissionError("Access denied: Lesson notes are only accessible to enrolled students.")

    # For now, DBMS CS304 is the provided subject note
    if "dbms" in subject.lower() or "cs304" in subject.lower() or "database" in subject.lower():
        text_source = DBMS_NOTES_TEXT
    else:
        text_source = DBMS_NOTES_TEXT

    results = _keyword_search(text_source, query, max_snippets=3)
    return f"Lesson Notes ({subject}) Excerpt:\n{results}"

