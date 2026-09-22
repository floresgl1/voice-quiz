# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Voice Quiz is a web-based study tool that quizzes users via text-to-speech, accepts spoken answers via speech-to-text, and uses the Claude API to grade responses. Stack: Python FastAPI backend + single-page HTML/JS frontend (no framework).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server (serves frontend at http://localhost:8000)
uvicorn main:app --reload

# Run a single module check
python -c "from main import app"
```

There are no tests, linter, or type checker configured yet.

## Setup

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Optionally set `CLAUDE_MODEL` (defaults to `claude-sonnet-5`).

## Architecture

Session results are persisted in SQLite (`./data/voicequiz.db`) via `database.py`. Quiz-time state (queue position, current question) lives in the frontend JavaScript; the DB stores sessions, questions, and grading attempts for history.

**Request flow:**

1. `POST /upload` — accepts PDF/DOCX, extracts text (`extraction.py`), sends to Claude to generate questions (`claude_client.py` using prompt from `prompts.py`), stores session + questions in SQLite, returns `{session_id, questions}`
2. `POST /grade` — accepts question + expected answer + user answer (+ optional session_id, question_db_id, attempt_num), sends to Claude for grading, persists attempt to DB, returns `{judgment, score, explanation}`
3. `POST /skip` — records a skipped attempt in the DB
4. `POST /update-score` — updates session total_points in the DB
5. `POST /complete-session` — marks session as completed in the DB
6. `POST /explain` — accepts question + expected answer + user attempts, sends to Claude for a teaching-style concept breakdown (plain text, not JSON)
7. `GET /sessions` — list past quiz sessions (date, source file, score)
8. `GET /sessions/{id}` — full session detail with per-question results and attempts
9. `GET /` — serves `index.html`

**Frontend state machine:** upload → loading → quiz → summary. TTS uses browser `SpeechSynthesis`, STT uses browser `SpeechRecognition` (Chrome only).

**Persistence** is handled by `database.py` — plain `sqlite3`, no ORM. Tables: `sessions`, `questions`, `attempts`. DB auto-created on startup via `init_db()`.

**Claude API calls** go through `claude_client.py`, which handles response parsing. Claude sometimes wraps JSON in markdown code blocks — `_parse_json()` handles both raw JSON and fenced blocks.

**Prompt templates** live in `prompts.py`. The generation prompt requests structured JSON with `id`, `question`, `expected_answer`, `topic`, `difficulty`. The grading prompt requests `judgment`, `score`, `explanation` and instructs leniency for speech-transcription artifacts.

## Data Model

Question object (backend returns, frontend augments during quiz):
- Backend fields: `id`, `question`, `expected_answer`, `topic`, `difficulty`, and optionally `diagram` (inline SVG circuit schematic) + `diagram_alt` (spoken description of it)
- Frontend adds: `status` (pending/graded/skipped), `user_answer`, `judgment`, `score`, `explanation`, `retries`, `bestScore`, `attempts[]`, `db_id` (from server)

Score model: 1.0 (correct), 0.5 (partially correct), 0.0 (incorrect/skipped). Displayed as points.

## Key Constraints

- Browser target is Chrome (Web Speech API for STT requires it and requires internet)
- File uploads limited to PDF and DOCX
- `expected_answer` is sent to the frontend in the question object (visible in DevTools — acceptable for a personal study tool)
- v1.1 retry loop: incorrect/skipped questions re-enter the queue (interleaved, max 2 retries, best score kept)
- v1.2 concept explainer: after exhausting retries, "Help me understand" calls `/explain` for a teaching breakdown with code examples
- v2.0 persistence: SQLite stores sessions, questions, and attempts; history view lets user review past quizzes
- Circuit diagrams: Claude may attach an inline SVG `diagram` to a circuit question. All model-generated SVG passes through `svg_sanitize.py` (whitelist of tags/attributes, local refs only) before it reaches the browser — a diagram that fails to sanitize, or arrives without `diagram_alt`, is dropped and the question is used as-is. Diagrams use `currentColor` so they work in both themes; `diagram_alt` is spoken by TTS and sent to the grader/explainer as context. The PDF export prints the description, not the SVG (fpdf2 drops `<text>` from SVG, which would strip component labels)
- See `requirements.md` for full v1 spec and `roadmap.md` for version planning
