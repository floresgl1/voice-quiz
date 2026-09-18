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
from claude_client import generate_questions, grade_answer, explain_concept, generate_choices
from youtube import get_transcript
from github import get_repo_content
from database import init_db, create_session, save_attempt, update_session_score, complete_session, get_sessions, get_session_detail, create_flag, update_session_max_points, get_flags, update_question, delete_question

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
async def upload(files: list[UploadFile] = File(...), num_questions: int = Form(10)):
    num_questions = max(1, min(30, num_questions))
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
            questions = generate_questions(text, num_questions)
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


class GenerateFromTextRequest(BaseModel):
    text: str
    num_questions: int = 10


@app.post("/generate")
def generate_from_text(req: GenerateFromTextRequest):
    num_questions = max(1, min(30, req.num_questions))
    text = req.text.strip()
    if not text:
        raise HTTPException(422, "No text provided")

    try:
        questions = generate_questions(text, num_questions)
    except ValueError as e:
        log.exception("Failed to parse generated questions from pasted text")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error for pasted text")
        raise HTTPException(502, f"AI service error: {e}")

    for q in questions:
        q["source_file"] = "Pasted text"

    result = create_session("Pasted text", questions)
    return {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }


class GenerateFromURLRequest(BaseModel):
    url: str
    num_questions: int = 10


@app.post("/generate-from-url")
def generate_from_url(req: GenerateFromURLRequest):
    num_questions = max(1, min(30, req.num_questions))
    url = req.url.strip()
    if not url:
        raise HTTPException(422, "No URL provided")

    is_github = "github.com" in url
    is_youtube = "youtube.com" in url or "youtu.be" in url

    if not is_github and not is_youtube:
        raise HTTPException(422, "URL must be a YouTube video or GitHub repository")

    try:
        if is_github:
            text, source_label = get_repo_content(url)
        else:
            text = get_transcript(url)
            source_label = url
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("Failed to fetch content from %s", url)
        raise HTTPException(502, f"Could not fetch content: {e}")

    try:
        questions = generate_questions(text, num_questions)
    except ValueError as e:
        log.exception("Failed to parse generated questions from URL source")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error for URL source")
        raise HTTPException(502, f"AI service error: {e}")

    for q in questions:
        q["source_file"] = source_label

    result = create_session(source_label, questions)
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


class UpdateQuestionRequest(BaseModel):
    question: str
    expected_answer: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None


@app.put("/sessions/{session_id}/questions/{question_id}")
def edit_question(session_id: int, question_id: int, req: UpdateQuestionRequest):
    update_question(question_id, req.question, req.expected_answer, req.topic, req.difficulty)
    return {"status": "ok"}


@app.delete("/sessions/{session_id}/questions/{question_id}")
def remove_question(session_id: int, question_id: int):
    delete_question(question_id, session_id)
    return {"status": "ok"}


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


class GenerateChoicesRequest(BaseModel):
    questions: list[dict]


@app.post("/generate-choices")
def gen_choices(req: GenerateChoicesRequest):
    try:
        choices = generate_choices(req.questions)
    except Exception as e:
        log.exception("Failed to generate MC choices")
        raise HTTPException(502, f"AI service error: {e}")
    return {"choices": choices}


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
