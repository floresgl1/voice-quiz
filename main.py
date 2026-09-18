from dotenv import load_dotenv

load_dotenv()

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extraction import extract_text
from claude_client import generate_questions, grade_answer, explain_concept
from database import init_db, create_session, save_attempt, update_session_score, complete_session, get_sessions, get_session_detail, create_flag, update_session_max_points, get_flags

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
async def upload(files: list[UploadFile] = File(...)):
    all_questions = []
    warnings = []
    source_names = []

    for file in files:
        filename = file.filename or "unknown"
        suffix = _get_extension(filename)
        if suffix not in ALLOWED_EXTENSIONS:
            warnings.append(f"{filename}: unsupported file type ({suffix})")
            continue

        contents = await file.read()
        text = extract_text(contents, suffix)
        if not text.strip():
            warnings.append(f"{filename}: could not extract any text")
            continue

        try:
            questions = generate_questions(text)
        except ValueError as e:
            log.exception("Failed to parse generated questions for %s", filename)
            warnings.append(f"{filename}: failed to generate questions")
            continue
        except Exception as e:
            log.exception("Claude API error for %s", filename)
            warnings.append(f"{filename}: AI service error")
            continue

        for q in questions:
            q["source_file"] = filename
        all_questions.extend(questions)
        source_names.append(filename)

    if not all_questions:
        detail = "No questions could be generated."
        if warnings:
            detail += " Warnings: " + "; ".join(warnings)
        raise HTTPException(422, detail)

    session_label = ", ".join(source_names)
    result = create_session(session_label, all_questions)
    response = {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }
    if warnings:
        response["warnings"] = warnings
    return response


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


class FlagRequest(BaseModel):
    session_id: int
    question_db_id: int
    flag_type: str
    override_judgment: Optional[str] = None
    score_delta: Optional[float] = None
    note: Optional[str] = None


@app.post("/flag")
def flag_question(req: FlagRequest):
    create_flag(req.question_db_id, req.flag_type, req.override_judgment, req.note)
    if req.flag_type == "bad_question":
        update_session_max_points(req.session_id, -1)
    if req.score_delta is not None and req.score_delta != 0:
        from database import _connect
        conn = _connect()
        conn.execute("UPDATE sessions SET total_points = total_points + ? WHERE id = ?", (req.score_delta, req.session_id))
        conn.commit()
        conn.close()
    return {"status": "ok"}


@app.get("/flags")
def list_flags():
    return get_flags()


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
