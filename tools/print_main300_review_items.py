from __future__ import annotations

import json
from pathlib import Path


RUN = Path("reports/product_eval/main-dialogue-300-full-20260504-025041")
results = json.loads((RUN / "cases.json").read_text(encoding="utf-8"))["results"]

for i, result in enumerate(results, start=1):
    actual = (result.get("actual") or "").replace("\n", " ")[:650]
    print(
        f"#{i:03d} {result['case_id']} module={result.get('module')} feature={result.get('feature')} "
        f"auto={result.get('status')}"
    )
    print("SUMMARY:", result.get("summary"))
    print("EXPECTED:", result.get("expected_result"))
    print("ACTUAL:", actual)
    print("---")
