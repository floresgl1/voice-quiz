# Voice Quiz App — Roadmap

## v1 — MVP (current build)
**Goal:** A working study tool you'd actually use.

### Definition of Done
- [ ] Can upload a PDF or .docx and get quiz questions back
- [ ] System generates 10 questions by default (fewer for short sources)
- [ ] Questions are read aloud and displayed on screen
- [ ] Can record a voice answer and see the transcription
- [ ] Can skip a question when you don't know the answer
- [ ] Answer gets graded by Claude with a judgment + explanation
- [ ] Partial credit works (0.5 points) and shows what was right / what was missing
- [ ] Score tracks correctly as points through a full session
- [ ] Session ends after one pass through all questions, or when user clicks "End Quiz"
- [ ] Summary screen shows final score and per-question breakdown
- [ ] Loading indicator shown during upload and question generation
- [ ] Errors displayed to the user (upload failure, API failure, STT failure)
- [ ] Runs locally (FastAPI + browser) with no manual JSON editing

---

## v1.1 — Retry Loop
**Goal:** Let missed questions come back for another attempt.

- [x] Incorrect and skipped questions re-enter the queue (interleaved, not after a full pass)
- [x] Max 2 retries per question
- [x] Best score kept across attempts; totalPoints tracks the delta
- [x] Session ends when queue is empty or user clicks "End Quiz"
- [x] Retry indicator shown on retried questions; summary shows retry count

---

## v1.2 — Concept Explainer
**Goal:** Help you learn from questions you couldn't answer after retries.

- [x] After exhausting 2 retries on a question, show a "Help me understand" button
- [x] Calls a new `/explain` endpoint that sends the question, expected answer, and user's attempts to Claude
- [x] Claude returns a teaching-style breakdown: why the answer is correct, the underlying concept, and what to review
- [x] Include code examples and snippets when applicable (e.g., for programming or technical questions)
- [x] Explanation displayed inline in the feedback section

---

## v2.0 — Persistence Foundation
**Goal:** Add SQLite so session results survive a browser refresh and can be reviewed later.

- [ ] New `database.py` — plain `sqlite3`, no ORM. DB at `./data/voicequiz.db`
- [ ] Schema: `sessions`, `questions`, `attempts` tables
- [ ] `POST /upload` returns a `session_id`; stores session + questions in DB
- [ ] `POST /grade` accepts `session_id` + `question_id`, writes attempt row
- [ ] `GET /sessions` — list past sessions (date, source file, score)
- [ ] `GET /sessions/{id}` — full session detail with per-question results
- [ ] Frontend sends `session_id` with grading/explain requests
- [ ] "History" button on upload screen → session list view

---

## v2.1 — Multi-File Upload
**Goal:** Accept multiple files and tag questions by source.

- [ ] `POST /upload` accepts multiple files (processed sequentially)
- [ ] `source_file` column on questions table
- [ ] Frontend file input gets `multiple` attribute; button shows file count
- [ ] Score bar shows source file label on current question
- [ ] Summary groups/tags results by source file

---

## v2.2 — AI Quality Flagging
**Goal:** Let the user flag bad questions or bad grading during a quiz.

- [ ] "Flag Question" button — removes from queue, doesn't count against score
- [ ] "Flag Grading" button — user overrides grade, score recalculated
- [ ] `flags` table + `POST /flag` and `GET /flags` endpoints
- [ ] Flagged questions visually distinct in summary

---

## v2.3 — Question Editing
**Goal:** Review and tweak AI-generated questions before starting the quiz.

- [ ] "Review Questions" screen between upload and quiz (with "Skip Review" option)
- [ ] Editable cards: question text, expected answer, topic, difficulty
- [ ] Can delete a question (adjusts max_points)
- [ ] `PUT` and `DELETE` endpoints for questions

---

## Future (unscoped)
- Rich question formatting (render formulas, symbols, and code snippets properly — e.g., KaTeX for math, inline code styling)
- User accounts / multi-user support
- Spaced repetition (resurface questions you got wrong days later)
- Multiple answer modes (multiple choice, typed, voice)
- Custom voice selection and speech rate
- Deployment / hosting
- GitHub repo ingestion (paste a URL, filter relevant files, chunk for LLM context)
- Configurable question count
- Export / share session results
- Re-quiz from the same source with fresh questions
