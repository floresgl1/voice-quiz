import json
import os
import re

import anthropic

from prompts import build_generation_prompt, build_grading_prompt, build_explain_prompt, build_choices_prompt, build_review_summary_prompt

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


def generate_review_summary(missed_questions: list[dict]) -> str:
    prompt = build_review_summary_prompt(missed_questions)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return _extract_text(response)


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


def _fix_latex_escapes(text: str) -> str:
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_ch = text[i + 1]
            if next_ch == '\\':
                result.append('\\\\')
                i += 2
                continue
            if next_ch == '"':
                result.append('\\"')
                i += 2
                continue
            if next_ch == 'u' and i + 5 < len(text) and all(c in '0123456789abcdefABCDEF' for c in text[i+2:i+6]):
                result.append(text[i:i+6])
                i += 6
                continue
            result.append('\\\\')
            i += 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


def _fix_newlines_in_strings(text: str) -> str:
    result = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\' and in_string:
            escaped = True
            result.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
        if in_string and ch == '\n':
            result.append('\\n')
            continue
        result.append(ch)
    return ''.join(result)


def _parse_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract JSON from code fence — use greedy match to handle nested backticks
    match = re.search(r"```(?:json)?\s*\n([\s\S]*)\n\s*```\s*$", text)
    if not match:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    raw = match.group(1) if match else text

    for fixer in [
        lambda t: t,
        _fix_latex_escapes,
        lambda t: _fix_newlines_in_strings(_fix_latex_escapes(t)),
    ]:
        try:
            return json.loads(fixer(raw))
        except (json.JSONDecodeError, ValueError):
            continue

    raise ValueError(f"Could not parse JSON from response: {text[:200]}")
