from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class StabilityEvent:
    kind: str
    line: str


CRASH_PATTERNS = [
    re.compile(r"FATAL EXCEPTION"),
    re.compile(r"\bAndroidRuntime\b.*\bFATAL\b"),
    re.compile(r"\bAndroidRuntime\b.*\bException\b", re.IGNORECASE),
]

ANR_PATTERNS = [
    re.compile(r"\bANR in\b"),
    re.compile(r"Application Not Responding"),
    re.compile(r"Input dispatching timed out"),
]


def scan_stability_events(log_path: Path) -> List[StabilityEvent]:
    if not log_path.exists():
        return []
    events: List[StabilityEvent] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if any(pattern.search(line) for pattern in CRASH_PATTERNS):
            events.append(StabilityEvent("crash", line[:500]))
        elif any(pattern.search(line) for pattern in ANR_PATTERNS):
            events.append(StabilityEvent("anr", line[:500]))
    return events
