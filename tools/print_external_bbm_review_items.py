from __future__ import annotations

import json
from pathlib import Path


RUN = Path("reports/product_eval/main-dialogue-external-bbm-50-20260504-105026")
results = json.loads((RUN / "cases.json").read_text(encoding="utf-8"))["results"]
external = json.loads(
    Path("reports/product_eval/main_dialogue_external_empirical_wrong_50_20260504.json").read_text(
        encoding="utf-8"
    )
)

for i, (result, source) in enumerate(zip(results, external), start=1):
    actual = (result.get("actual") or "").replace("\n", " ")[:700]
    print(
        f"#{i:02d} {result['case_id']} task={source['task']} "
        f"target={source['target']!r} external_wrong={source['source_model_wrong_answer']!r} "
        f"auto={result['status']}"
    )
    print("ACTUAL:", actual)
    print("---")
