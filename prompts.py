def build_generation_prompt(source_text: str, num_questions: int = 10) -> str:
    return f"""You are a study quiz generator. Given the source material below, generate {num_questions} quiz questions that test understanding of the key concepts.

Return ONLY a JSON array of question objects. Each object must have:
- "id": integer starting at 1
- "question": a clear, specific question
- "expected_answer": a concise but complete reference answer
- "topic": a short category label for the question
- "difficulty": one of "easy", "medium", or "hard"

Rules:
- Prioritize conceptual questions that test understanding, reasoning, and application — ask "why," "how," "explain," "compare," "what would happen if"
- Avoid pure recall questions like "list," "name," "define," or "what is X" — unless the concept genuinely requires a definition to demonstrate understanding
- Vary the difficulty across questions
- Each question should be answerable from the source material
- Expected answers should be 1-3 sentences
- If the source material is too short for {num_questions} questions, generate as many as the material supports

Source material:
{source_text}"""


def build_grading_prompt(question: str, expected_answer: str, user_answer: str) -> str:
    return f"""You are grading a spoken quiz answer. Compare the student's answer to the expected answer.

Question: {question}

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
- "incorrect" means the answer is wrong or doesn't address the question"""
