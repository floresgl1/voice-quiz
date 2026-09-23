from dotenv import load_dotenv

load_dotenv()

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from extraction import extract_text
from claude_client import generate_questions, grade_answer, explain_concept, generate_choices, generate_review_summary, generate_lesson
from youtube import get_transcript
from github import get_repo_content
from database import init_db, create_session, save_attempt, update_session_score, complete_session, get_sessions, get_session_detail, get_source_text, get_quiz_state, save_quiz_state, create_flag, update_session_max_points, get_flags, update_question, delete_question

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


def _api_key(header_val: str | None) -> str | None:
    key = header_val or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(401, "No API key provided. Enter your Anthropic API key in Settings.")
    return header_val


def _user_hash(header_val: str | None) -> str | None:
    key = header_val or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    return hashlib.sha256(key.encode()).hexdigest()[:16]


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def index():
    # The whole app is one file; never let a browser serve a stale copy of it.
    return FileResponse(ROOT / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "has_server_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/upload")
async def upload(files: list[UploadFile] = File(...), num_questions: int = Form(10), x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    num_questions = max(1, min(30, num_questions))
    all_questions = []
    all_texts = []
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
            questions = generate_questions(text, num_questions, api_key=api_key)
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
        all_texts.append(text)
        source_names.append(filename)

    if not all_questions:
        detail = "No questions could be generated."
        if warnings:
            detail += " Warnings: " + "; ".join(warnings)
        raise HTTPException(422, detail)

    session_label = ", ".join(source_names)
    combined_text = "\n\n".join(all_texts)
    result = create_session(session_label, all_questions, source_text=combined_text, user_hash=_user_hash(x_api_key))
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
def generate_from_text(req: GenerateFromTextRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    num_questions = max(1, min(30, req.num_questions))
    text = req.text.strip()
    if not text:
        raise HTTPException(422, "No text provided")

    try:
        questions = generate_questions(text, num_questions, api_key=api_key)
    except ValueError as e:
        log.exception("Failed to parse generated questions from pasted text")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error for pasted text")
        raise HTTPException(502, f"AI service error: {e}")

    for q in questions:
        q["source_file"] = "Pasted text"

    result = create_session("Pasted text", questions, source_text=text, user_hash=_user_hash(x_api_key))
    return {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }


class GenerateFromURLRequest(BaseModel):
    url: str
    num_questions: int = 10


@app.post("/generate-from-url")
def generate_from_url(req: GenerateFromURLRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
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
        questions = generate_questions(text, num_questions, api_key=api_key)
    except ValueError as e:
        log.exception("Failed to parse generated questions from URL source")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error for URL source")
        raise HTTPException(502, f"AI service error: {e}")

    for q in questions:
        q["source_file"] = source_label

    result = create_session(source_label, questions, source_text=text, user_hash=_user_hash(x_api_key))
    return {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }


class RequizRequest(BaseModel):
    session_id: int
    num_questions: int = 10


@app.post("/requiz")
def requiz(req: RequizRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    num_questions = max(1, min(30, req.num_questions))
    text = get_source_text(req.session_id)
    if not text:
        raise HTTPException(404, "No source text found for this session")

    detail = get_session_detail(req.session_id)
    source_label = detail["source_file"] if detail else "Re-quiz"

    try:
        questions = generate_questions(text, num_questions, api_key=api_key)
    except ValueError as e:
        log.exception("Failed to parse re-quiz questions")
        raise HTTPException(502, f"Failed to generate questions: {e}")
    except Exception as e:
        log.exception("Claude API error during re-quiz")
        raise HTTPException(502, f"AI service error: {e}")

    for q in questions:
        q["source_file"] = source_label

    result = create_session(source_label, questions, source_text=text, user_hash=_user_hash(x_api_key))
    return {
        "session_id": result["session_id"],
        "questions": result["questions"],
    }


class GradeRequest(BaseModel):
    question: str
    expected_answer: str
    user_answer: str
    diagram_alt: Optional[str] = None
    session_id: Optional[int] = None
    question_db_id: Optional[int] = None
    attempt_num: Optional[int] = None


@app.post("/grade")
def grade(req: GradeRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    try:
        result = grade_answer(req.question, req.expected_answer, req.user_answer, api_key=api_key,
                              diagram_alt=req.diagram_alt)
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


class UpdateMaxPointsRequest(BaseModel):
    session_id: int
    max_points: int


@app.post("/update-max-points")
def update_max(req: UpdateMaxPointsRequest):
    from database import _connect
    conn = _connect()
    conn.execute("UPDATE sessions SET max_points = ? WHERE id = ?", (req.max_points, req.session_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


class CompleteSessionRequest(BaseModel):
    session_id: int
    total_points: float


@app.post("/complete-session")
def complete(req: CompleteSessionRequest):
    complete_session(req.session_id, req.total_points)
    return {"status": "ok"}


@app.get("/sessions")
def list_sessions(x_api_key: Optional[str] = Header(None)):
    return get_sessions(user_hash=_user_hash(x_api_key))


@app.get("/sessions/{session_id}")
def session_detail(session_id: int):
    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(404, "Session not found")
    return detail


@app.get("/sessions/{session_id}/export-pdf")
def export_pdf(session_id: int, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    from pdf_export import generate_study_sheet

    detail = get_session_detail(session_id)
    if not detail:
        raise HTTPException(404, "Session not found")

    questions = detail.get("questions", [])
    missed = [
        q for q in questions
        if not q.get("flag") and q.get("attempts") and q["best_score"] < 1.0
    ]

    review_summary = None
    if missed:
        try:
            review_summary = generate_review_summary(missed, api_key=api_key)
        except Exception:
            log.exception("Failed to generate review summary")

    pdf_bytes = generate_study_sheet(detail, review_summary)
    filename = f"study-sheet-{session_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    from transcribe import transcribe_audio
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(422, "No audio data received")
    try:
        text = transcribe_audio(audio_bytes, audio.content_type or "audio/webm")
    except Exception as e:
        log.exception("Transcription failed")
        raise HTTPException(502, f"Transcription failed: {e}")
    return {"text": text}


class SaveStateRequest(BaseModel):
    session_id: int
    state: Optional[dict] = None


@app.post("/save-state")
def save_state(req: SaveStateRequest):
    import json
    save_quiz_state(req.session_id, json.dumps(req.state) if req.state else None)
    return {"status": "ok"}


@app.get("/sessions/{session_id}/state")
def get_state(session_id: int):
    import json
    state_json = get_quiz_state(session_id)
    if not state_json:
        raise HTTPException(404, "No saved state for this session")
    return json.loads(state_json)


class GenerateChoicesRequest(BaseModel):
    questions: list[dict]


@app.post("/generate-choices")
def gen_choices(req: GenerateChoicesRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    try:
        choices = generate_choices(req.questions, api_key=api_key)
    except Exception as e:
        log.exception("Failed to generate MC choices")
        raise HTTPException(502, f"AI service error: {e}")
    return {"choices": choices}


class ExplainRequest(BaseModel):
    question: str
    expected_answer: str
    user_attempts: list[str]
    diagram_alt: Optional[str] = None


@app.post("/explain")
def explain(req: ExplainRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    try:
        explanation = explain_concept(req.question, req.expected_answer, req.user_attempts, api_key=api_key,
                                      diagram_alt=req.diagram_alt)
    except Exception as e:
        log.exception("Claude API error during explanation")
        raise HTTPException(502, f"AI service error: {e}")
    return {"explanation": explanation}


class FailedCheck(BaseModel):
    check_question: str
    user_answer: str


class LearnRequest(BaseModel):
    question: str
    expected_answer: str
    user_attempts: list[str]
    diagram_alt: Optional[str] = None
    failed_checks: list[FailedCheck] = []


@app.post("/learn")
def learn(req: LearnRequest, x_api_key: Optional[str] = Header(None)):
    api_key = _api_key(x_api_key)
    try:
        result = generate_lesson(req.question, req.expected_answer, req.user_attempts, api_key=api_key,
                                 diagram_alt=req.diagram_alt,
                                 failed_checks=[c.model_dump() for c in req.failed_checks])
    except ValueError as e:
        log.exception("Failed to parse lesson response")
        raise HTTPException(502, f"Failed to generate lesson: {e}")
    except Exception as e:
        log.exception("Claude API error during lesson generation")
        raise HTTPException(502, f"AI service error: {e}")
    return result


def _get_extension(filename: str | None) -> str:
    if not filename:
        return ""
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()
