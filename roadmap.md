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

## v2 — Persistence & Quality Control
**Goal:** Remember what happened and catch AI mistakes.

### Tracking & History
- Store session results (date, source file, score)
- Store per-question results (question, your answer, grade, explanation)
- Review past sessions to identify weak areas

### Multi-File Upload
- Upload multiple files at once
- Each file generates its own batch of questions (scaled per file)
- Questions tagged by source file

### AI Quality Flagging
- Flag a bad question (nonsensical or unanswerable) — skip and remove from pool
- Flag bad grading (correct answer marked wrong, or vice versa) — override the grade
- Save flags for review to improve generation/grading prompts over time

### Question Editing
- Review and tweak AI-generated questions before quizzing
- Edit question text or expected answers

---

## Future (unscoped)
- User accounts / multi-user support
- Spaced repetition (resurface questions you got wrong days later)
- Multiple answer modes (multiple choice, typed, voice)
- Custom voice selection and speech rate
- Deployment / hosting
- GitHub repo ingestion (paste a URL, filter relevant files, chunk for LLM context)
- Configurable question count
- Export / share session results
- Re-quiz from the same source with fresh questions
