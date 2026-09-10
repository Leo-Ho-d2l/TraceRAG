from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.llm.client import get_chat_client


@dataclass(slots=True)
class JudgeResult:
    correctness: float
    groundedness: float
    citation_quality: float
    reason: str


JUDGE_SYSTEM = """You are evaluating an enterprise RAG answer.
Return JSON only with numeric fields correctness, groundedness, citation_quality in [0,1], plus a short reason.
Correctness: whether the answer addresses the question and matches the expected facts.
Groundedness: whether answer claims are supported by the supplied cited excerpts.
Citation quality: whether citations are attached to relevant claims and use only supplied labels.
Do not reward verbosity.
"""


async def judge_answer(
    question: str,
    expected_facts: list[str],
    answer: str,
    citations: list[dict],
) -> JudgeResult:
    client = get_chat_client()
    evidence = "\n\n".join(
        f"[{c['label']}] {c['filename']} | {c.get('section_title') or ''}\n{c['excerpt']}"
        for c in citations
    )
    result = await client.chat(
        [
            {"role": "system", "content": JUDGE_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\nExpected facts: {expected_facts}\n\n"
                    f"Answer:\n{answer}\n\nCited evidence:\n{evidence}"
                ),
            },
        ],
        temperature=0.0,
    )
    payload = _json(result.content or "")
    return JudgeResult(
        correctness=_score(payload.get("correctness")),
        groundedness=_score(payload.get("groundedness")),
        citation_quality=_score(payload.get("citation_quality")),
        reason=str(payload.get("reason", ""))[:500],
    )


def _json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _score(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
