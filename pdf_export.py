import io
import re
from fpdf import FPDF, XPos, YPos


NX = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}


class StudySheetPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 6, self._header_text, align="R", **NX)
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\$\$(.+?)\$\$', r'[\1]', text, flags=re.DOTALL)
    text = re.sub(r'\$(.+?)\$', r'[\1]', text)
    text = re.sub(r'```\w*\n?', '', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.encode('latin-1', errors='replace').decode('latin-1')
    return text.strip()


def _diagram_note(pdf, q):
    """Describe a circuit diagram in words.

    The on-screen diagram is inline SVG, but fpdf2's SVG support ignores <text>,
    which would strip every component label from a printed schematic. The
    description is lossy but honest.
    """
    alt = q.get("diagram_alt")
    if not alt:
        return
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 5, f"Circuit shown: {_clean_text(alt)}", **NX)


def generate_study_sheet(session: dict, review_summary: str | None = None) -> bytes:
    pdf = StudySheetPDF()
    pdf.alias_nb_pages()
    pdf._header_text = f"Study Sheet - {session['source_file']}"
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 12, "Study Review Sheet", align="C", **NX)
    pdf.ln(4)

    # Session info
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    source = _clean_text(session["source_file"])
    pdf.cell(0, 6, f"Source: {source}", align="C", **NX)
    pdf.cell(0, 6, f"Date: {session['created_at'][:10]}", align="C", **NX)

    questions = session.get("questions", [])
    scored = [q for q in questions if not q.get("flag") and q.get("attempts")]

    total = session.get("total_points", 0)
    max_pts = len(scored)
    pdf.cell(0, 6, f"Score: {total} / {max_pts}", align="C", **NX)
    pdf.ln(6)

    # Divider
    pdf.set_draw_color(200, 200, 200)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    # Categorize questions
    missed = []
    partial = []
    mastered = []

    for q in questions:
        if q.get("flag"):
            continue
        best = q.get("best_score", 0)
        attempts = q.get("attempts", [])
        if not attempts:
            continue
        elif best >= 1.0:
            mastered.append(q)
        elif best >= 0.5:
            partial.append(q)
        else:
            missed.append(q)

    def group_by_topic(qs):
        groups = {}
        for q in qs:
            topic = q.get("topic") or "General"
            if topic not in groups:
                groups[topic] = []
            groups[topic].append(q)
        return groups

    # Section 1: Missed & Partial
    needs_review = missed + partial
    if needs_review:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(200, 50, 50)
        pdf.cell(0, 10, "Needs Review", **NX)
        pdf.ln(2)

        for topic, qs in group_by_topic(needs_review).items():
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 7, _clean_text(topic), **NX)

            for q in qs:
                best = q.get("best_score", 0)
                label = "Partial" if best >= 0.5 else "Incorrect"
                last_attempt = q["attempts"][-1] if q.get("attempts") else {}
                user_ans = last_attempt.get("user_answer", "No answer")
                explanation = last_attempt.get("explanation", "")

                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 5, f"Q: {_clean_text(q['question'])}", **NX)
                _diagram_note(pdf, q)

                pdf.set_font("Helvetica", "I", 9)
                color = (200, 140, 0) if best >= 0.5 else (200, 50, 50)
                pdf.set_text_color(*color)
                pdf.cell(0, 5, f"[{label} - {best} pts]", **NX)

                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(100, 100, 100)
                pdf.multi_cell(0, 5, f"Your answer: {_clean_text(user_ans)}", **NX)

                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 100, 30)
                pdf.multi_cell(0, 5, f"Correct answer: {_clean_text(q['expected_answer'])}", **NX)

                if explanation:
                    pdf.set_font("Helvetica", "I", 9)
                    pdf.set_text_color(60, 60, 60)
                    pdf.multi_cell(0, 5, f"Explanation: {_clean_text(explanation)}", **NX)

                pdf.ln(4)

    # Section 2: Mastered
    if mastered:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 140, 60)
        pdf.cell(0, 10, "Mastered", **NX)
        pdf.ln(2)

        for topic, qs in group_by_topic(mastered).items():
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(80, 80, 80)
            pdf.cell(0, 6, _clean_text(topic), **NX)

            for q in qs:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 5, f"  {_clean_text(q['question'])}", **NX)
                _diagram_note(pdf, q)
                pdf.ln(1)

        pdf.ln(4)

    # Section 3: Key Concepts to Review
    if review_summary:
        pdf.set_draw_color(200, 200, 200)
        pdf.line(20, pdf.get_y(), 190, pdf.get_y())
        pdf.ln(6)

        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 80, 180)
        pdf.cell(0, 10, "Key Concepts to Review", **NX)
        pdf.ln(2)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        for line in review_summary.strip().split("\n"):
            line = line.strip()
            if line:
                pdf.multi_cell(0, 6, _clean_text(line), **NX)
                pdf.ln(2)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
