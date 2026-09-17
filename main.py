from dotenv import load_dotenv

load_dotenv()

import logging

from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extraction import extract_text
from claude_client import generate_questions, grade_answer

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
    return questions


class GradeRequest(BaseModel):
    question: str
    expected_answer: str
    user_answer: str


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
    return result


def _get_extension(filename: str | None) -> str:
    if not filename:
        return ""
    dot = filename.rfind(".")
    if dot == -1:
        return ""
    return filename[dot:].lower()
