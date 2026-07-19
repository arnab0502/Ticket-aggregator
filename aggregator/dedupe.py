"""Cross-source duplicate detection and price comparison.

Two events are considered the same listing if they are in the same city
and their normalized titles are similar enough (fuzzy match). Matched
groups get a shared `group_id` so the dashboard can show a price
comparison across sources.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

STOPWORDS = {
    "live", "show", "shows", "the", "a", "an", "in", "at", "by", "ft", "feat",
    "featuring", "of", "and", "standup", "stand", "up", "comedy", "solo", "tour",
}
SIMILARITY_THRESHOLD = 0.78


def normalize(title: str) -> str:
    import html
    t = re.sub(r"[^a-z0-9 ]", " ", html.unescape(title).lower())
    words = [w for w in t.split() if w not in STOPWORDS]
    return " ".join(words)


def similar(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    # Containment: "shashi dhiman" ⊂ "out order shashi dhiman" is a match.
    wa, wb = set(a.split()), set(b.split())
    small, big = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if len(small) >= 2 and small <= big:
        return True
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


def assign_groups(events: list[dict]) -> list[dict]:
    """Mutates events: adds group_id and duplicate flags. Returns events."""
    norms = [normalize(e["title"]) for e in events]
    group_of = [-1] * len(events)
    next_group = 0

    for i in range(len(events)):
        if group_of[i] != -1:
            continue
        group_of[i] = next_group
        for j in range(i + 1, len(events)):
            if group_of[j] == -1 and events[i]["city"] == events[j]["city"] and similar(norms[i], norms[j]):
                group_of[j] = next_group
        next_group += 1

    counts: dict[int, set] = {}
    for idx, g in enumerate(group_of):
        counts.setdefault(g, set()).add(events[idx]["source"])

    for idx, e in enumerate(events):
        g = group_of[idx]
        e["group_id"] = g
        e["multi_source"] = len(counts[g]) > 1
    return events
