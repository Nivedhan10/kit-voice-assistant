# Knotopian Institute of Technology (KIT) — Real-Time Voice Assistant

Production-grade, real-time voice assistant for **Knotopian Institute of Technology (KIT)**. Built with FastAPI, strictly adhering to enterprise security standards, zero Web Speech API usage, deterministic rule validation, server-enforced confirmations, and multi-tier resilience.

> For the comprehensive architectural specification, security boundaries, and rule references, see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## 1. System Architecture

The assistant operates under a clear separation of concerns across audio capture, authentication, agent orchestration, rule validation, and persistence:

```
[Browser Audio: MediaRecorder (WebM/WAV)]
              │
              ▼
[FastAPI Gateway: /api/v1/voice/chat]
              │
              ├─► Session & RBAC Layer (Signed HttpOnly Cookies, Role Isolation)
              │
              ├─► Speech-to-Text Layer (External Whisper API / Fallback Engine)
              │
              ├─► Agent Orchestrator & State Machine
              │         │
              │         ├─► Pure Business Rules (validate_leave_request)
              │         ├─► Scoped Knowledge Retrieval (Brochure, Handbook, Notes)
              │         └─► College System Client (Authenticated Tool Invocations)
              │
              ├─► Text-to-Speech Layer (External TTS-1 / Graceful Text Fallback)
              │
              └─► Conversation Persistence (PostgreSQL / SQLite Audit Store)
```

---

## 2. Tool Registry & RBAC Permissions Matrix

The table below is generated directly from `app/agent/registry.py`, ensuring zero drift between code execution and permissions:

| Tool Name | Allowed Roles | Needs Confirmation? | Backend / College Endpoint |
|---|---|---|---|
| `search_admission_brochure` | `public`, `student`, `teacher` | No | `Internal KB (Admissions Brochure 2026)` |
| `get_available_courses` | `public`, `student`, `teacher` | No | `GET /v1/courses` |
| `get_college_overview` | `public`, `student`, `teacher` | No | `GET /v1/college` |
| `submit_admission_application` | `public` | **Yes** | `POST /v1/admissions/applications` |
| `get_student_attendance` | `student` | No | `GET /v1/me/attendance` |
| `get_student_academics` | `student` | No | `GET /v1/me/academics` |
| `get_academic_schedule` | `student`, `teacher` | No | `GET /v1/me/timetable | GET /v1/calendar` |
| `apply_leave_or_od` | `student` | **Yes** | `POST /v1/me/requests` |
| `get_my_requests` | `student` | No | `GET /v1/me/requests` |
| `cancel_leave_request` | `student` | **Yes** | `POST /v1/me/requests/{id}/cancel` |
| `search_college_handbook` | `student`, `teacher` | No | `Internal KB (Handbook 2026 & Circular 12/2026)` |
| `search_lesson_notes` | `student` | No | `Internal KB (DBMS CS304 Notes)` |
| `get_placement_drives` | `student` | No | `GET /v1/placements/drives` |
| `register_placement_drive` | `student` | **Yes** | `POST /v1/placements/drives/{id}/register` |
| `get_my_placement_registrations` | `student` | No | `GET /v1/me/placements` |
| `get_teacher_classes` | `teacher` | No | `GET /v1/teacher/classes` |
| `get_class_attendance_sheet` | `teacher` | No | `GET /v1/teacher/classes/{class_id}/attendance` |
| `get_assigned_pending_requests` | `teacher` | No | `GET /v1/teacher/requests` |
| `decide_student_request` | `teacher` | **Yes** | `POST /v1/teacher/requests/{id}/approve | reject` |

---

## 3. Key Design Decisions

### 3.1 Strict Security & Identity Decoupling
- **No Identity in Tool Schemas:** Tool schemas do not accept `student_id` or `user_id`. Identity is injected exclusively from the authenticated server-side session.
- **Token Protection:** College API Bearer tokens are kept in server-side memory only. The browser receives a signed `httpOnly`, `SameSite=Lax` session cookie.
- **Untrusted Context Isolation:** Prompts explicitly declare that tool outputs, database notes, and user voice inputs are untrusted data. Prompt injection traps (e.g. malicious student notes commanding approvals) are safely treated as passive text.

### 3.2 Pure Business Rules in Code
- Academic regulations are codified in `app/rules/leave_validator.py` as pure, deterministic functions:
  - **Rule 6.1.1:** Personal leave must be applied $\ge 24$ hours in advance; retrospective personal leave is blocked.
  - **Rule 6.1.4:** Personal leave is blocked on exam days (`internal_exam`, `end_semester_exam`).
  - **Rule 6.4.7:** On-Duty is blocked during exams without Principal approval.
  - **Rule 6.4.5:** Maximum 10 working days on-duty per semester.
  - **Circular 12/2026:** Event proof for B.Tech On-Duty must be submitted within 3 working days (overriding Handbook Rule 6.4.3).
  - **Rule 4.1.1 & 4.2.3:** Attendance minimum 75% check; warns when planned leave causes attendance to fall into condonation/detention bands.

### 3.3 Two-Step Server-Enforced Confirmation
- All write actions (`apply_leave_or_od`, `submit_admission_application`, `decide_student_request`, `register_placement_drive`, `cancel_leave_request`) require a two-step flow.
- A `pending_action` object is stored in the server session with an expiry TTL.
- The action only executes when the user confirms on the subsequent turn (*"Yes"*, *"Confirm"*, *"Proceed"*). Transcription errors on dates and names never execute prematurely.

### 3.4 Speech & Multi-Tier Fallback Resilience
- **No Web Speech API:** Speech recognition uses external speech services via `MediaRecorder` audio uploads.
- **Multi-Provider STT Chain:**
  1. Primary: Groq (`whisper-large-v3-turbo` — 150ms transcription speed)
  2. Secondary: Groq (`whisper-large-v3`)
  3. Tertiary: OpenAI Whisper (`whisper-1`)
  - Skips empty keys automatically; logs errors server-side only.
- **Config-Driven Multi-Provider LLM Chain:**
  1. Primary: Groq (`llama-3.3-70b-versatile` with tool calling enabled)
  2. Secondary: Google Gemini (`gemini-2.5-flash` via AI Studio OpenAI-compatible endpoint)
  3. Tertiary: OpenAI (`gpt-4o-mini`)
- **Text-to-Speech (TTS):**
  - Primary: `edge-tts` (neural voice `en-US-JennyNeural`, zero API key required, high quality).
  - Guaranteed Fallback: Returns text transcript with HTTP 200 without ever crashing.
- **Deterministic Resilience Engine:** If external AI services experience rate-limits (HTTP 429) or timeouts, the system automatically activates a deterministic fallback engine that queries the College API directly and provides immediate spoken answers.

---

## 4. Local Setup & Quickstart

### Prerequisites
- Python 3.10+
- College System API Key

### Installation
```bash
# Clone repository
git clone <repo-url>
cd Quirri

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
```

### Running the App
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser:
- **Home & Admissions:** [http://localhost:8000/](http://localhost:8000/)
- **Student & Teacher Portal:** [http://localhost:8000/portal](http://localhost:8000/portal)
- **History Logs:** [http://localhost:8000/history](http://localhost:8000/history)

---

## 5. Deploying to Render + Neon

The service is pre-configured for automated deployment on **Render** (as a long-running Python Web Service) backed by **Neon PostgreSQL** (for zero-maintenance serverless persistence).

### Environment Variables Matrix

| Variable Name | Required? | Default / Example | Purpose |
|---|---|---|---|
| `COLLEGE_API_KEY` | **Yes** | `kit_live_...` | Participant key for Knotopian Institute of Technology API |
| `COLLEGE_API_BASE_URL` | No | `https://ht.knowvally.com` | Base URL for college system endpoints |
| `GROQ_API_KEY` | **Yes** | `gsk_...` | Primary STT (Whisper Large v3) and primary LLM (LLaMA 3.3) |
| `GEMINI_API_KEY` | No | `AIza...` | Secondary LLM fallback via Google AI Studio |
| `OPENAI_API_KEY` | No | `sk-...` | Tertiary cloud backup for speech and LLM |
| `PRIMARY_LLM_MODEL` | No | `openai/gpt-oss-120b` | Primary LLM model identifier |
| `FALLBACK_LLM_MODEL` | No | `openai/gpt-oss-20b` | Fallback LLM model identifier |
| `PRIMARY_STT_MODEL` | No | `whisper-large-v3-turbo` | Primary Whisper STT model |
| `FALLBACK_STT_MODEL` | No | `whisper-large-v3` | Secondary Whisper STT model |
| `TTS_PROVIDER` | No | `edge_tts` | Text-to-speech provider (`edge_tts` or `openai`) |
| `EDGE_TTS_VOICE` | No | `en-US-JennyNeural` | Voice identifier for Microsoft Edge Neural TTS |
| `SESSION_SECRET_KEY` | **Yes** | *(random 48-char secret)* | HMAC key used to sign `kit_session_id` cookies |
| `SESSION_COOKIE_NAME` | No | `kit_session_id` | Name of the session cookie |
| `SESSION_MAX_AGE_SECONDS`| No | `28800` | Cookie lifetime (8 hours, matching college auth token) |
| `COOKIE_SECURE` | No | `true` (prod) / `false` (dev) | Enforces `Secure` flag on HTTPS deployments |
| `DATABASE_URL` | **Yes** (prod) | `postgresql://user:pass@ep-xyz.neon.tech/neondb?sslmode=require` | Neon PostgreSQL pooled connection string (falls back to SQLite offline) |
| `MIN_ATTENDANCE_PERCENT` | No | `75.0` | Handbook Rule 4.1.1 attendance eligibility threshold |
| `MAX_OD_DAYS_PER_SEMESTER`| No | `10` | Handbook Rule 6.4.5 semester on-duty cap |
| `OD_PROOF_DEADLINE_DAYS` | No | `3` | Circular 12/2026 on-duty proof submission window |

### Setup Instructions

1. **Generate Session Secret:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. **Neon Database Connection String:**
   Create a free project at [neon.tech](https://neon.tech) and copy the **Pooled connection string**:
   ```
   postgresql://user:password@ep-xyz.neon.tech/neondb?sslmode=require
   ```
   *(Note: The app automatically normalizes legacy `postgres://` URLs to `postgresql://` and sets `pool_pre_ping=True` to seamlessly handle Neon's scale-to-zero wakeups).*
3. **Render Web Service Settings:**
   * **Runtime:** Python 3
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   * **Health Check Path:** `/health`
   * *(Note: Free-tier instances spin down after inactivity; initial cold starts may take ~30 seconds).*

---

## 6. Test User Accounts

| Role | Username | Authentication | Notes |
|---|---|---|---|
| Student | `arjun` | *College SSO Credentials (Access Card)* | 2nd Year CSE-2A, Attendance: 76.0% (Eligible) |
| Student | `priya` | *College SSO Credentials (Access Card)* | 2nd Year CSE-2A, Attendance: 70.0% (Shortage Warning) |
| Student | `kavya` | *College SSO Credentials (Access Card)* | 2nd Year CSE-2A |
| Teacher | `lakshmi` | *College SSO Credentials (Access Card)* | Class Advisor for CSE-2A (3 Pending Approvals) |
| Teacher | `senthil` | *College SSO Credentials (Access Card)* | Department Faculty |

---

## 7. Running the Automated Test Suite

All tests run offline using mocks and evaluate RBAC security, rule enforcement, confirmation states, prompt injection defenses, Postgres URL normalization, and fallback handlers:

```bash
pytest -v
```

All 26 test cases pass completely offline in under 3 seconds.

