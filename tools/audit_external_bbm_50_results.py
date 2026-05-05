from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-external-bbm-50-20260504-105026"
EXTERNAL_JSON = ROOT / "reports" / "product_eval" / "main_dialogue_external_empirical_wrong_50_20260504.json"


def norm(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def md_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def main() -> int:
    cases = json.loads((RUN_DIR / "cases.json").read_text(encoding="utf-8"))["results"]
    external = json.loads(EXTERNAL_JSON.read_text(encoding="utf-8"))
    targets = {f"MD-EXT-BBM-{i:03d}": item for i, item in enumerate(external, start=1)}

    audited: list[dict[str, Any]] = []
    for case in cases:
        source = targets[case["case_id"]]
        target = source["target"]
        actual = case.get("actual", "")
        target_n = norm(target)
        actual_n = norm(actual)
        if target_n and actual_n == target_n:
            audit_status = "correct_exact"
        elif target_n and target_n in actual_n:
            audit_status = "correct_contains"
        elif not actual_n:
            audit_status = "no_answer"
        else:
            audit_status = "wrong_or_needs_review"
        audited.append(
            {
                "case_id": case["case_id"],
                "task": source["task"],
                "target": target,
                "lingxi_actual": actual,
                "source_model_wrong_answer": source["source_model_wrong_answer"],
                "auto_status": case["status"],
                "audit_status": audit_status,
                "response_screenshot": case.get("response_screenshot"),
                "complete_ms": case.get("response_complete_time_ms"),
            }
        )

    counts: dict[str, int] = {}
    for item in audited:
        counts[item["audit_status"]] = counts.get(item["audit_status"], 0) + 1

    lines = [
        "# 外部实测错题 50 题复核表",
        "",
        f"- Run dir: `{RUN_DIR}`",
        f"- 复核规则: 去除空白后，灵犀实际答案与 BIG-Bench Mistake 标准答案完全相同为 `correct_exact`；实际回答包含标准答案为 `correct_contains`；其他为 `wrong_or_needs_review`。",
        "",
        "## 复核汇总",
        "",
        "| 状态 | 数量 |",
        "| --- | ---: |",
    ]
    for key in ["correct_exact", "correct_contains", "wrong_or_needs_review", "no_answer"]:
        lines.append(f"| {key} | {counts.get(key, 0)} |")

    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| ID | 任务 | 标准答案 | 灵犀实际答案 | 外部模型错误答案 | 自动状态 | 复核状态 | 完成 ms | 截图 |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for item in audited:
        lines.append(
            f"| {item['case_id']} | {item['task']} | {md_cell(item['target'], 80)} | "
            f"{md_cell(item['lingxi_actual'], 120)} | {md_cell(item['source_model_wrong_answer'], 80)} | "
            f"{item['auto_status']} | {item['audit_status']} | {item.get('complete_ms', '')} | {md_cell(item.get('response_screenshot'), 80)} |"
        )

    (RUN_DIR / "external_bbm_50_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RUN_DIR / "external_bbm_50_audit.json").write_text(
        json.dumps({"counts": counts, "results": audited}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
