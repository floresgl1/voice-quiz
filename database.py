import sqlite3
import os
from datetime import datetime, timezone

DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(__file__), "data"))
DB_PATH = os.path.join(DB_DIR, "voicequiz.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT    NOT NULL,
            source_file  TEXT    NOT NULL,
            total_points REAL    NOT NULL DEFAULT 0,
            max_points   INTEGER NOT NULL DEFAULT 0,
            completed    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL REFERENCES sessions(id),
            position        INTEGER NOT NULL,
            question        TEXT    NOT NULL,
            expected_answer TEXT    NOT NULL,
            topic           TEXT,
            difficulty      TEXT,
            source_file     TEXT
        );

        CREATE TABLE IF NOT EXISTS flags (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id       INTEGER NOT NULL REFERENCES questions(id),
            flag_type         TEXT    NOT NULL,
            override_judgment TEXT,
            note              TEXT,
            created_at        TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attempts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            attempt_num INTEGER NOT NULL,
            user_answer TEXT,
            judgment    TEXT    NOT NULL,
            score       REAL    NOT NULL,
            explanation TEXT,
            created_at  TEXT    NOT NULL
        );
    """)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "source_text" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN source_text TEXT")
    if "quiz_state" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN quiz_state TEXT")

    conn.commit()
    conn.close()


def create_session(source_file: str, questions: list[dict], source_text: str | None = None) -> dict:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO sessions (created_at, source_file, max_points, source_text) VALUES (?, ?, ?, ?)",
        (now, source_file, len(questions), source_text),
    )
    session_id = cur.lastrowid

    db_questions = []
    for i, q in enumerate(questions):
        cur = conn.execute(
            "INSERT INTO questions (session_id, position, question, expected_answer, topic, difficulty, source_file) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, i + 1, q["question"], q["expected_answer"], q.get("topic"), q.get("difficulty"), q.get("source_file")),
        )
        db_questions.append({**q, "db_id": cur.lastrowid})

    conn.commit()
    conn.close()
    return {"session_id": session_id, "questions": db_questions}


def save_attempt(question_id: int, attempt_num: int, user_answer: str | None,
                 judgment: str, score: float, explanation: str | None) -> int:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO attempts (question_id, attempt_num, user_answer, judgment, score, explanation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (question_id, attempt_num, user_answer, judgment, score, explanation, now),
    )
    attempt_id = cur.lastrowid
    conn.commit()
    conn.close()
    return attempt_id


def update_question(question_id: int, question: str, expected_answer: str, topic: str | None, difficulty: str | None):
    conn = _connect()
    conn.execute(
        "UPDATE questions SET question = ?, expected_answer = ?, topic = ?, difficulty = ? WHERE id = ?",
        (question, expected_answer, topic, difficulty, question_id),
    )
    conn.commit()
    conn.close()


def delete_question(question_id: int, session_id: int):
    conn = _connect()
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.execute("UPDATE sessions SET max_points = max_points - 1 WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def update_session_score(session_id: int, total_points: float):
    conn = _connect()
    conn.execute("UPDATE sessions SET total_points = ? WHERE id = ?", (total_points, session_id))
    conn.commit()
    conn.close()


def complete_session(session_id: int, total_points: float):
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET completed = 1, total_points = ? WHERE id = ?",
        (total_points, session_id),
    )
    conn.commit()
    conn.close()


def create_flag(question_id: int, flag_type: str, override_judgment: str | None = None, note: str | None = None) -> int:
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO flags (question_id, flag_type, override_judgment, note, created_at) VALUES (?, ?, ?, ?, ?)",
        (question_id, flag_type, override_judgment, note, now),
    )
    flag_id = cur.lastrowid
    conn.commit()
    conn.close()
    return flag_id


def update_session_max_points(session_id: int, delta: int):
    conn = _connect()
    conn.execute("UPDATE sessions SET max_points = max_points + ? WHERE id = ?", (delta, session_id))
    conn.commit()
    conn.close()


def get_flags() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT f.id, f.question_id, f.flag_type, f.override_judgment, f.note, f.created_at, q.question "
        "FROM flags f JOIN questions q ON f.question_id = q.id ORDER BY f.created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_quiz_state(session_id: int, state_json: str):
    conn = _connect()
    conn.execute("UPDATE sessions SET quiz_state = ? WHERE id = ?", (state_json, session_id))
    conn.commit()
    conn.close()


def get_quiz_state(session_id: int) -> str | None:
    conn = _connect()
    row = conn.execute("SELECT quiz_state FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row["quiz_state"] if row else None


def get_source_text(session_id: int) -> str | None:
    conn = _connect()
    row = conn.execute("SELECT source_text FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return row["source_text"] if row else None


def get_sessions() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, created_at, source_file, total_points, max_points, completed FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_detail(session_id: int) -> dict | None:
    conn = _connect()
    session = conn.execute(
        "SELECT id, created_at, source_file, total_points, max_points, completed FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if not session:
        conn.close()
        return None

    questions = conn.execute(
        "SELECT id, position, question, expected_answer, topic, difficulty, source_file FROM questions WHERE session_id = ? ORDER BY position",
        (session_id,),
    ).fetchall()

    result = dict(session)
    result["questions"] = []
    for q in questions:
        qd = dict(q)
        attempts = conn.execute(
            "SELECT attempt_num, user_answer, judgment, score, explanation, created_at FROM attempts WHERE question_id = ? ORDER BY attempt_num",
            (q["id"],),
        ).fetchall()
        qd["attempts"] = [dict(a) for a in attempts]
        qd["best_score"] = max((a["score"] for a in qd["attempts"]), default=0)
        flag = conn.execute(
            "SELECT flag_type, override_judgment, note FROM flags WHERE question_id = ? ORDER BY created_at DESC LIMIT 1",
            (q["id"],),
        ).fetchone()
        qd["flag"] = dict(flag) if flag else None
        result["questions"].append(qd)

    conn.close()
    return result
