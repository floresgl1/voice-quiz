def build_generation_prompt(source_text: str, num_questions: int = 10) -> str:
    return f"""You are a study quiz generator. Given the source material below, generate {num_questions} quiz questions that test understanding of the key concepts.

Return ONLY a JSON array of question objects. Each object must have:
- "id": integer starting at 1
- "question": a clear, specific question
- "expected_answer": a concise but complete reference answer
- "topic": a short category label for the question
- "difficulty": one of "easy", "medium", or "hard"
- "diagram": (OPTIONAL) inline SVG markup for a circuit diagram, when the question is about a circuit
- "diagram_alt": (REQUIRED if "diagram" is present) a one-sentence spoken description of the circuit, since the question is read aloud

Rules:
- Prioritize conceptual questions that test understanding, reasoning, and application — ask "why," "how," "explain," "compare," "what would happen if"
- Avoid pure recall questions like "list," "name," "define," or "what is X" — unless the concept genuinely requires a definition to demonstrate understanding
- Vary the difficulty across questions
- Each question should be answerable from the source material
- Expected answers should be 1-3 sentences
- If the source material is too short for {num_questions} questions, generate as many as the material supports
- When the source contains math, formulas, or equations, use LaTeX notation in questions and answers: inline math with $...$ and display math with $$...$$
- When the source contains code, use triple-backtick code blocks with the language name (e.g. ```python) in questions and answers

Circuit diagrams:
- Include a "diagram" ONLY when the question is genuinely about a circuit and the student needs to see it to answer — e.g. "in the circuit shown, what happens to Vout if R2 doubles?". Never add a diagram as decoration, and never for non-circuit material.
- Omit the "diagram" and "diagram_alt" keys entirely for every other question.
- The question text must refer to the diagram (e.g. "in the circuit shown") rather than restating the whole topology.
- Draw with plain SVG primitives only: <svg>, <g>, <line>, <polyline>, <polygon>, <path>, <rect>, <circle>, <ellipse>, <text>. No <style>, <script>, <foreignObject>, CSS classes, or external references — they are stripped.
- The root <svg> MUST have a viewBox (e.g. viewBox="0 0 320 200") and MUST NOT have width or height; the page sizes it.
- Use stroke="currentColor" and fill="none" for wires and component bodies, and fill="currentColor" for <text> and for solid junction dots, so the diagram works in both light and dark themes. Never use hard-coded colors like black or #000.
- Use stroke-width="2", font-size="13", and keep labels (R1, 10k, Vin, Vout, GND) clear of the wires.
- Draw standard symbols: resistor as a zigzag <polyline>, capacitor as two parallel plates, battery/DC source as alternating long and short plates, ground as three shrinking horizontal bars, wires as straight horizontal or vertical <line> segments meeting at right angles, junctions as small filled circles (r="3").
- Keep it small and readable — under about 10 components.

Source material:
{source_text}"""


def build_grading_prompt(question: str, expected_answer: str, user_answer: str,
                         diagram_alt: str | None = None) -> str:
    circuit = f"\nCircuit shown with the question: {diagram_alt}\n" if diagram_alt else ""
    return f"""You are grading a spoken quiz answer. Compare the student's answer to the expected answer.

Question: {question}
{circuit}
Expected answer: {expected_answer}

Student's answer: {user_answer}

Return ONLY a JSON object with:
- "judgment": one of "correct", "partially_correct", or "incorrect"
- "score": 1.0 for correct, 0.5 for partially_correct, 0.0 for incorrect
- "explanation": 1-2 sentences explaining what the student got right and what was missing

Grading guidelines:
- Be lenient with phrasing — the answer was spoken aloud and transcribed, so minor wording differences are expected
- "correct" means the student captured the key concept(s), even if worded differently
- "partially_correct" means the student got some key points but missed others
- "incorrect" means the answer is wrong or doesn't address the question
- Use LaTeX ($...$ for inline, $$...$$ for display) for any math in the explanation
- Use triple-backtick code blocks for any code in the explanation"""


def build_choices_prompt(questions: list[dict]) -> str:
    q_list = "\n".join(
        f'{i+1}. Q: {q["question"]}\n'
        + (f'   Circuit shown: {q["diagram_alt"]}\n' if q.get("diagram_alt") else "")
        + f'   A: {q["expected_answer"]}'
        for i, q in enumerate(questions)
    )
    return f"""For each question below, generate 4 multiple-choice options: one correct answer and three plausible distractors.

Return ONLY a JSON array where each element is an array of 4 strings (the choices). The correct answer should be randomly placed among the 4 options (not always first). Distractors should be wrong but realistic.

Questions:
{q_list}"""


def build_review_summary_prompt(missed_questions: list[dict]) -> str:
    items = "\n".join(
        f'{i+1}. Topic: {q.get("topic", "General")}\n'
        f'   Question: {q["question"]}\n'
        f'   Expected answer: {q["expected_answer"]}\n'
        f'   Student answered: {q.get("user_answer", "N/A")}'
        for i, q in enumerate(missed_questions)
    )
    return f"""A student just completed a quiz and got the following questions wrong or only partially correct. Based on these missed questions, write a concise study review.

Missed/partial questions:
{items}

Write 3-5 bullet points summarizing the key concepts the student needs to review. Each bullet should:
- Name the specific concept or topic
- Give a one-sentence explanation of what to focus on
- Be actionable (e.g. "Review how X works" not just "X")

Return ONLY the bullet points as plain text, one per line, starting with "- ". Keep it concise and useful — this goes on a printed study sheet. Do NOT use LaTeX or code blocks."""


def build_explain_prompt(question: str, expected_answer: str, user_attempts: list[str],
                         diagram_alt: str | None = None) -> str:
    attempts_text = "\n".join(f"- Attempt {i+1}: {a}" for i, a in enumerate(user_attempts))
    circuit = f"\nCircuit shown with the question: {diagram_alt}\n" if diagram_alt else ""
    return f"""You are a patient tutor helping a student understand a concept they struggled with on a quiz. They attempted this question multiple times and still didn't get it right.

Question: {question}
{circuit}
Expected answer: {expected_answer}

Student's attempts:
{attempts_text}

Write a clear, teaching-style explanation that helps the student understand this concept. Your response should be plain text (not JSON) with this structure:

1. Start with a brief, friendly explanation of the core concept (2-3 sentences)
2. Explain why the expected answer is correct and what the student may have been missing
3. If the topic is technical or programming-related, include a short code example or snippet that illustrates the concept — use triple backticks with the language name for formatting
4. End with a one-sentence suggestion of what to review or practice

Keep the tone encouraging. The goal is to help them learn, not to grade them again."""


def build_learn_prompt(question: str, expected_answer: str, user_attempts: list[str],
                       diagram_alt: str | None = None, failed_checks: list[dict] | None = None) -> str:
    attempts_text = "\n".join(f"- Attempt {i+1}: {a}" for i, a in enumerate(user_attempts)) or "- (skipped)"
    circuit = f"\nCircuit shown with the question: {diagram_alt}\n" if diagram_alt else ""
    retry = ""
    if failed_checks:
        checks_text = "\n".join(
            f'- Check question: {c["check_question"]}\n  Student answered: {c["user_answer"]}'
            for c in failed_checks
        )
        retry = f"""
You already taught this concept and the student failed these check questions afterward:
{checks_text}

Your previous explanation did not land. Teach it from a DIFFERENT angle this time — a new analogy, a worked example, or breaking it into smaller steps. Do not repeat the same explanation.
"""
    return f"""You are a patient tutor. A student just finished a quiz and missed this question. Teach them the concept, then check whether they understood it.

Quiz question: {question}
{circuit}
Expected answer: {expected_answer}

Student's attempts:
{attempts_text}
{retry}
Return ONLY a JSON object with:
- "lesson": a short teaching explanation (under 200 words). Explain the core concept, why the expected answer is correct, and what the student's attempts were missing. Include a short code example in triple backticks if the topic is programming-related. Use LaTeX ($...$) for math.
- "check_question": ONE new question that tests the SAME concept. It must NOT be a rewording of the quiz question, and its answer must NOT appear verbatim in the lesson — the student should have to apply the concept, not recall a sentence they just read. It will be read aloud and answered by voice, so keep it short and answerable in one or two spoken sentences.
- "check_expected_answer": the answer to check_question, used for grading"""
