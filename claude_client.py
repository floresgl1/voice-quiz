import json
import os
import re

import anthropic

from prompts import build_generation_prompt, build_grading_prompt, build_explain_prompt, build_choices_prompt

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

client = anthropic.Anthropic()


def generate_questions(source_text: str, num_questions: int = 10) -> list[dict]:
    prompt = build_generation_prompt(source_text, num_questions)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    questions = _parse_json(text)
    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array of questions")
    return questions


def grade_answer(question: str, expected_answer: str, user_answer: str) -> dict:
    prompt = build_grading_prompt(question, expected_answer, user_answer)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    result = _parse_json(text)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object for grading result")
    return result


def generate_choices(questions: list[dict]) -> list[list[str]]:
    prompt = build_choices_prompt(questions)

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    choices = _parse_json(text)
    if not isinstance(choices, list):
        raise ValueError("Expected a JSON array of choice arrays")
    return choices


def explain_concept(question: str, expected_answer: str, user_attempts: list[str]) -> str:
    prompt = build_explain_prompt(question, expected_answer, user_attempts)

    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return _extract_text(response)


def _extract_text(response) -> str:
    for block in response.content:
        if block.type == "text":
            return block.text
    raise ValueError("No text block in Claude response")


def _parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError(f"Could not parse JSON from response: {text[:200]}")
