import json
import os
import re

import anthropic

from svg_sanitize import sanitize_svg
from prompts import build_generation_prompt, build_grading_prompt, build_explain_prompt, build_choices_prompt, build_review_summary_prompt, build_learn_prompt

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

_default_client = None


def _get_client(api_key: str | None = None) -> anthropic.Anthropic:
    if api_key:
        return anthropic.Anthropic(api_key=api_key)
    global _default_client
    if _default_client is None:
        _default_client = anthropic.Anthropic()
    return _default_client


def generate_questions(source_text: str, num_questions: int = 10, api_key: str | None = None) -> list[dict]:
    prompt = build_generation_prompt(source_text, num_questions)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        # Circuit diagrams are inline SVG, which is token-hungry.
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    questions = _parse_json(text)
    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array of questions")

    for q in questions:
        if not isinstance(q, dict):
            continue
        diagram = sanitize_svg(q.get("diagram"))
        if diagram and q.get("diagram_alt"):
            q["diagram"] = diagram
        else:
            # An unusable or unlabelled diagram is dropped; the question still works.
            q.pop("diagram", None)
            q.pop("diagram_alt", None)

    return questions


def grade_answer(question: str, expected_answer: str, user_answer: str, api_key: str | None = None,
                 diagram_alt: str | None = None) -> dict:
    prompt = build_grading_prompt(question, expected_answer, user_answer, diagram_alt)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    result = _parse_json(text)
    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object for grading result")
    return result


def generate_choices(questions: list[dict], api_key: str | None = None) -> list[list[str]]:
    prompt = build_choices_prompt(questions)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    choices = _parse_json(text)
    if not isinstance(choices, list):
        raise ValueError("Expected a JSON array of choice arrays")
    return choices


def generate_review_summary(missed_questions: list[dict], api_key: str | None = None) -> str:
    prompt = build_review_summary_prompt(missed_questions)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    return _extract_text(response)


def explain_concept(question: str, expected_answer: str, user_attempts: list[str], api_key: str | None = None,
                    diagram_alt: str | None = None) -> str:
    prompt = build_explain_prompt(question, expected_answer, user_attempts, diagram_alt)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    return _extract_text(response)


def generate_lesson(question: str, expected_answer: str, user_attempts: list[str], api_key: str | None = None,
                    diagram_alt: str | None = None, failed_checks: list[dict] | None = None) -> dict:
    prompt = build_learn_prompt(question, expected_answer, user_attempts, diagram_alt, failed_checks)

    response = _get_client(api_key).messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    text = _extract_text(response)
    result = _parse_json(text)
    if not isinstance(result, dict) or not all(
        result.get(k) for k in ("lesson", "check_question", "check_expected_answer")
    ):
        raise ValueError("Expected a JSON object with lesson, check_question, check_expected_answer")
    return result


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
