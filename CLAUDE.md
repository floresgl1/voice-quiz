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

The backend is stateless — all session state (question pool, scores, current index) lives in the frontend JavaScript.

**Request flow:**

1. `POST /upload` — accepts PDF/DOCX, extracts text (`extraction.py`), sends to Claude to generate questions (`claude_client.py` using prompt from `prompts.py`), returns JSON array of question objects
2. `POST /grade` — accepts question + expected answer + user answer, sends to Claude for grading, returns `{judgment, score, explanation}`
3. `GET /` — serves `index.html`

**Frontend state machine:** upload → loading → quiz → summary. TTS uses browser `SpeechSynthesis`, STT uses browser `SpeechRecognition` (Chrome only).

**Claude API calls** go through `claude_client.py`, which handles response parsing. Claude sometimes wraps JSON in markdown code blocks — `_parse_json()` handles both raw JSON and fenced blocks.

**Prompt templates** live in `prompts.py`. The generation prompt requests structured JSON with `id`, `question`, `expected_answer`, `topic`, `difficulty`. The grading prompt requests `judgment`, `score`, `explanation` and instructs leniency for speech-transcription artifacts.

## Data Model

Question object (backend returns, frontend augments during quiz):
- Backend fields: `id`, `question`, `expected_answer`, `topic`, `difficulty`
- Frontend adds: `status` (pending/graded/skipped), `user_answer`, `judgment`, `score`, `explanation`

Score model: 1.0 (correct), 0.5 (partially correct), 0.0 (incorrect/skipped). Displayed as points.

## Key Constraints

- Browser target is Chrome (Web Speech API for STT requires it and requires internet)
- File uploads limited to PDF and DOCX
- `expected_answer` is sent to the frontend in the question object (visible in DevTools — acceptable for a personal study tool)
- No retry/re-queue of missed questions in v1 (deferred to v1.1)
- See `requirements.md` for full v1 spec and `roadmap.md` for version planning
