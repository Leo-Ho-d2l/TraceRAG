from __future__ import annotations

import re
from typing import Any


def heuristic_route(question: str) -> str:
    q = question.strip().lower()
    if re.fullmatch(r"(hi|hello|hey|thanks|thank you)[!. ]*", q):
        return "direct"
    if re.search(r"\b(compare|difference|versus|vs\.?|across|conflict|trade[- ]?off|why)\b", q):
        return "research"
    if q.count("?") > 1 or (" and " in q and len(q) > 120):
        return "research"
    return "retrieve"


def citations_are_valid(answer: str, evidence: list[dict[str, Any]]) -> bool:
    cited = set(re.findall(r"\[(S\d+)\]", answer))
    valid = {item["label"] for item in evidence}
    return bool(cited) and cited.issubset(valid)
