from dotenv import load_dotenv

load_dotenv()

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extraction import extract_text
from claude_client import generate_questions, grade_answer, explain_concept
from database import init_db, create_session, save_attempt, update_session_score, complete_session, get_sessions, get_session_detail

ROOT = Path(__file__).parent

log = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    suffix = _get_extension(file.filename)
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {suffix}")

    contents = await file.read()
    text = extract_text(contents, suffix)
    if not text.strip():
        raise HTTPException(422, "Could not extract any text from the file.")

    try:
        questions = generate_questions(text)
    except ValueError as e:
        log.exception("Failed to parse generated questions")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error during question generation")
        raise HTTPException(502, f"AI service error: {e}")

    result = create_session(file.filename or "unknown", questions)
    return {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }


class GradeRequest(BaseModel):
    question: str
    expected_answer: str
    user_answer: str
    session_id: Optional[int] = None
    question_db_id: Optional[int] = None
    attempt_num: Optional[int] = None


@app.post("/grade")
def grade(req: GradeRequest):
    try:
        result = grade_answer(req.question, req.expected_answer, req.user_answer)
    except ValueError as e:
        log.exception("Failed to parse grading response")
        raise HTTPException(502, f"Failed to grade answer: {e}")
    except Exception as e:
        log.exception("Claude API error during grading")
        raise HTTPException(502, f"AI service error: {e}")

    if req.question_db_id and req.attempt_num:
        save_attempt(
            req.question_db_id, req.attempt_num, req.user_answer,
            result["judgment"], result["score"], result.get("explanation"),
        )

    return result


class SkipRequest(BaseModel):
    session_id: int
    question_db_id: int
    attempt_num: int


@app.post("/skip")
def skip(req: SkipRequest):
    save_attempt(req.question_db_id, req.attempt_num, None, "skipped", 0.0, None)
    return {"status": "ok"}


class UpdateScoreRequest(BaseModel):
    session_id: int
    total_points: float


@app.post("/update-score")
def update_score(req: UpdateScoreRequest):
    update_session_score(req.session_id, req.total_points)
    return {"status": "ok"}


class CompleteSessionRequest(BaseModel):
    session_id: int
    total_points: float


@app.post("/complete-session")
def complete(req: CompleteSessionRequest):
    complete_session(req.session_id, req.total_points)
    return {"status": "ok"}


@app.get("/sessions")
def list_sessions():
    return get_sessions()


@app.get("/sessions/{session_id}")
def session_detail(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(404, "Session not found")
    return detail


class ExplainRequest(BaseModel):
    question: str
    expected_answer: str
    user_attempts: list[str]


@app.post("/explain")
def explain(req: ExplainRequest):
    try:
        explanation = explain_concept(req.question, req.expected_answer, req.user_attempts)
    except Exception as e:
        log.exception("Claude API error during explanation")
        raise HTTPException(502, f"AI service error: {e}")
    return {"explanation": explanation}


def _get_extension(filename: str | None) -> str:
    if not filename:
        return ""
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()
