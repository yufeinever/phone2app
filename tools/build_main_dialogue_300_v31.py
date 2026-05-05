from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "product_eval" / "main-dialogue-300-v3-20260505" / "cases.json"
ANSWERABILITY = ROOT / "reports" / "product_eval" / "main-dialogue-300-v3-answerability-audit-20260505" / "answerability_audit.json"
OUT_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-300-v3.1-20260505"


AMBIGUOUS_FIXES: dict[str, list[dict[str, str]]] = {
    "MD-X12": [
        {
            "input": "某病患病率为1%。检测灵敏度为100%，误阳性率为5%。一个人检测阳性后，是否一定是高概率患病？请直接回答并给出大约概率。",
            "expected": "不一定；在这些条件下阳性后患病概率约为16.8%或约17%，不是高概率。",
        }
    ],
    "MD-Q06": [
        {
            "input": "某病患病率为1%。检测灵敏度为100%，误阳性率为5%。检测阳性后是否一定高概率患病？请直接回答并给出大约概率。",
            "expected": "不一定；阳性后患病概率约为16.8%或约17%，需考虑基率和误阳性。",
        }
    ],
    "MD-EX-L24": [
        {
            "input": "“并非不允许提交”这句话在普通逻辑语义下是什么意思？请只回答“允许提交”或“不允许提交”。",
            "expected": "允许提交",
        }
    ],
}


OBJECTIVE_TYPES = {"objective_scoreable"}
RUBRIC_TYPES = {"rubric_needed", "rubric_scoreable"}


def text(value: Any) -> str:
    return str(value or "").strip()


def all_expected(case: dict[str, Any]) -> str:
    parts = [text(turn.get("expected")) for turn in case.get("turns", []) if text(turn.get("expected"))]
    return " / ".join(parts) if parts else text(case.get("expected_result"))


def split_expected(expected: str) -> list[str]:
    expected = re.sub(r"\s+", " ", expected).strip("。；; ")
    if not expected:
        return []
    raw_parts = re.split(r"\s*[；;]\s*|\s+/\s+", expected)
    parts = []
    for part in raw_parts:
        part = part.strip("。；; ")
        if not part:
            continue
        # Keep short exact answers together; split only broad comma lists.
        if len(part) > 24 and "，" in part:
            parts.extend(x.strip("。；; ") for x in part.split("，") if x.strip("。；; "))
        else:
            parts.append(part)
    seen = set()
    unique = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            unique.append(part)
    return unique


def make_rubric_items(expected: str) -> list[dict[str, Any]]:
    parts = split_expected(expected)
    if not parts:
        return [
            {
                "name": "人工复核",
                "points": 1,
                "must_have": ["回答与题目要求一致"],
                "fail_if": ["答非所问", "明显编造关键事实"],
            }
        ]
    items = []
    for idx, part in enumerate(parts, 1):
        items.append(
            {
                "name": f"检查点{idx}",
                "points": 1,
                "must_have": [part],
                "fail_if": ["遗漏该检查点", "给出与该检查点相反的结论"],
            }
        )
    return items


def apply_ambiguous_fix(case: dict[str, Any]) -> None:
    fix = AMBIGUOUS_FIXES.get(case["case_id"])
    if not fix:
        return
    case["turns"] = fix
    case["expected_result"] = " / ".join(turn["expected"] for turn in fix)
    case["v3_1_change"] = "修复 ambiguous 客观题：补齐条件或限定可接受答案。"


def apply_scoring(case: dict[str, Any], answerability: str) -> None:
    test_type = text(case.get("test_type"))
    mode = text(case.get("execution_mode"))
    expected = all_expected(case)

    if test_type == "product_operation" or mode == "uiautomator2_operation":
        case["scoring_type"] = "operation"
        case["operation_expected"] = case.get("operation_steps") or []
        case["score_rule"] = "按 operation_steps、截图/XML、响应时间和实际 UI 状态评价，不进入模型文本正确率。"
        return

    if test_type == "performance_collection" or mode == "uiautomator2_text_dialogue_with_metrics":
        case["scoring_type"] = "metric"
        case["metric_items"] = [
            "发送到首字响应时间",
            "发送到回答完成时间",
            "是否超时",
            "是否出现 Crash/ANR/卡死",
        ]
        case["score_rule"] = "按时延、超时和稳定性指标评价。"
        return

    if answerability in OBJECTIVE_TYPES or case["case_id"] in AMBIGUOUS_FIXES:
        case["scoring_type"] = "objective"
        case["strict_expected"] = expected
        case["score_rule"] = "只按 strict_expected 判定正确/错误；不使用 partial。"
        return

    if answerability in RUBRIC_TYPES:
        case["scoring_type"] = "rubric"
        case["rubric_items"] = make_rubric_items(expected)
        case["score_rule"] = "所有 rubric_items 均满足才计正确；任一必需检查点缺失则计错误；不使用 partial。"
        return

    case["scoring_type"] = "objective"
    case["strict_expected"] = expected
    case["score_rule"] = "只按 strict_expected 判定正确/错误；不使用 partial。"


def md_cell(value: Any, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip()).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    audit_rows = json.loads(ANSWERABILITY.read_text(encoding="utf-8"))["results"]
    answerability_by_id = {row["case_id"]: row["answerability"] for row in audit_rows}

    cases = payload["results"]
    for case in cases:
        apply_ambiguous_fix(case)
        apply_scoring(case, answerability_by_id.get(case["case_id"], "objective_scoreable"))

    if len(cases) != 300:
        raise RuntimeError(f"expected 300 cases, got {len(cases)}")
    ids = [case["case_id"] for case in cases]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        raise RuntimeError(f"duplicate case ids: {duplicates}")

    missing_scoring = [case["case_id"] for case in cases if not case.get("scoring_type")]
    if missing_scoring:
        raise RuntimeError(f"cases without scoring_type: {missing_scoring}")

    meta = dict(payload.get("metadata", {}))
    meta.update(
        {
            "name": "main-dialogue-300-v3.1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(SOURCE),
            "notes": [
                "v3.1 在 v3 基础上补齐评分元数据。",
                "所有题都有 scoring_type；开放题用 rubric_items；客观题用 strict_expected。",
                "3 道 ambiguous 题已补条件或限定答案。",
                "正式统计不使用 partial：rubric 必须全部满足才计正确。",
            ],
        }
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_payload = {"metadata": meta, "results": cases}
    (OUT_DIR / "cases.json").write_text(json.dumps(out_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    scoring_counts = Counter(case.get("scoring_type") for case in cases)
    module_counts = Counter(case.get("module") for case in cases)
    lines = [
        "# 主对话 300-v3.1 Summary",
        "",
        f"- 创建时间：{meta['created_at']}",
        "- 总题数：300",
        "- 修复 ambiguous 题：3",
        "- 补评分元数据题：300",
        "- 正式判分口径：不使用 partial；rubric 全部满足才计正确。",
        "",
        "## 按评分类型分布",
        "",
        "| 评分类型 | 数量 |",
        "| --- | ---: |",
    ]
    for key, value in scoring_counts.most_common():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## 按模块分布", "", "| 模块 | 数量 |", "| --- | ---: |"])
    for key, value in module_counts.most_common():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## ambiguous 修复明细", "", "| ID | 新题干 | 新预期 |", "| --- | --- | --- |"])
    for case in cases:
        if case["case_id"] in AMBIGUOUS_FIXES:
            lines.append(
                f"| {case['case_id']} | {md_cell(case['turns'][0]['input'], 120)} | {md_cell(case['turns'][0]['expected'], 100)} |"
            )
    (OUT_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(OUT_DIR / "cases.json")
    print(OUT_DIR / "summary.md")
    print(json.dumps({"scoring_counts": scoring_counts, "module_counts": module_counts}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
