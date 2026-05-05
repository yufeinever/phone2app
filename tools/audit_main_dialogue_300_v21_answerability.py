from __future__ import annotations

import json
import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.1-20260505" / "cases.json"
OUT_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.1-answerability-audit-20260505"


OBJECTIVE_MODULES = {"逻辑推理", "数学推理", "事实常识", "指令遵循", "主对话-历史错题"}
OBJECTIVE_FEATURE_WORDS = [
    "概率",
    "排序",
    "量词",
    "充分必要",
    "逆否",
    "方程",
    "百分比",
    "单位换算",
    "复杂度",
    "JSON",
    "固定格式",
    "禁止词",
    "精确数量",
    "首字约束",
    "末字约束",
    "不确定性",
]
OPEN_WORDS = [
    "摘要",
    "改写",
    "写作",
    "建议",
    "解释",
    "生成",
    "客服",
    "合规",
    "安抚",
    "测试用例",
    "错误处理",
]
VAGUE_WORDS = [
    "合理",
    "相关",
    "方向",
    "覆盖",
    "包含",
    "保留重点",
    "边界",
    "可用",
    "不编造",
    "不遗漏",
    "给一般原则",
    "提示风险",
    "安全替代",
    "更好",
    "完整",
    "清晰",
]


def text(value: Any) -> str:
    return str(value or "").strip()


def all_expected(case: dict[str, Any]) -> str:
    turns = case.get("turns") or []
    parts = [text(turn.get("expected")) for turn in turns if text(turn.get("expected"))]
    return " / ".join(parts) if parts else text(case.get("expected_result"))


def has_concrete_expected(expected: str) -> bool:
    if re.search(r"\d|[A-Z]{1,4}|[{}\\[\\]]|、|；|必须|只输出|正好|不超过|不能出现", expected):
        return True
    if len(expected) <= 12 and expected not in {"合理", "相关", "完整", "可用"}:
        return True
    return False


def classify(case: dict[str, Any]) -> tuple[str, str]:
    test_type = text(case.get("test_type"))
    mode = text(case.get("execution_mode"))
    scoring_type = text(case.get("scoring_type"))
    module = text(case.get("module"))
    feature = text(case.get("feature"))
    summary = text(case.get("summary"))
    expected = all_expected(case)
    joined = f"{module} {feature} {summary} {expected}"

    if scoring_type == "objective" and text(case.get("strict_expected")):
        return "objective_scoreable", "已提供 strict_expected，可按二分类判分。"
    if scoring_type == "rubric" and case.get("rubric_items"):
        return "rubric_scoreable", "已提供 rubric_items；全部满足计正确，不使用 partial。"
    if scoring_type == "metric" and case.get("metric_items"):
        return "metric_scoreable", "已提供 metric_items，可按时延/稳定性指标评价。"
    if scoring_type == "operation" and (case.get("operation_expected") or case.get("operation_steps")):
        return "operation_scoreable", "已提供操作步骤/预期，可按 UI 结果和证据评价。"

    if mode == "skip" or test_type == "metadata_only":
        return "not_scoreable", "元用例，不应进入模型评分。"
    if test_type == "product_operation" or mode == "uiautomator2_operation":
        return "not_scoreable", "产品操作/交互题，需按操作结果评价，不应按模型文本答案评分。"
    if test_type == "performance_collection":
        return "metric_scoreable", "性能采集题，应按首字/完成耗时等指标评分，不按语义正确率评分。"

    if not expected:
        return "ambiguous", "缺少 expected / 判分规则。"

    if module in OBJECTIVE_MODULES or any(word in joined for word in OBJECTIVE_FEATURE_WORDS):
        if has_concrete_expected(expected):
            return "objective_scoreable", "有明确答案或可程序化判分规则。"
        return "ambiguous", "看起来是客观题，但 expected 不够具体。"

    if any(word in joined for word in OPEN_WORDS):
        if sum(1 for word in VAGUE_WORDS if word in expected) >= 2 or len(expected) < 16:
            return "rubric_needed", "开放题只有概括性预期，需要拆成评分点。"
        return "rubric_scoreable", "开放题有基本约束，但建议改成多项 rubric。"

    if any(word in expected for word in VAGUE_WORDS):
        return "rubric_needed", "预期含模糊词，需要改成明确检查点。"

    return "objective_scoreable" if has_concrete_expected(expected) else "rubric_needed", "按启发式判断。"


def md_cell(value: Any, limit: int = 110) -> str:
    value = re.sub(r"\s+", " ", text(value)).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计主对话题库是否有明确标准答案或评分规则")
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))["results"]
    rows = []
    for case in data:
        category, reason = classify(case)
        rows.append(
            {
                "case_id": case["case_id"],
                "module": case.get("module"),
                "feature": case.get("feature"),
                "summary": case.get("summary"),
                "test_type": case.get("test_type"),
                "execution_mode": case.get("execution_mode"),
                "expected": all_expected(case),
                "answerability": category,
                "reason": reason,
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(args.source),
        },
        "counts": Counter(row["answerability"] for row in rows),
        "results": rows,
    }
    (args.out_dir / "answerability_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = Counter(row["answerability"] for row in rows)
    lines = [
        "# 主对话 300-v2.1 可判分性审计",
        "",
        f"- 创建时间：{payload['metadata']['created_at']}",
        f"- 源文件：`{args.source}`",
        "",
        "## 统计",
        "",
        "| 类别 | 数量 | 含义 |",
        "| --- | ---: | --- |",
        f"| objective_scoreable | {counts['objective_scoreable']} | 客观题，有明确答案或可程序化判分规则。 |",
        f"| rubric_scoreable | {counts['rubric_scoreable']} | 开放题有基本约束，但仍建议拆成 rubric。 |",
        f"| rubric_needed | {counts['rubric_needed']} | 开放题预期偏概括，需补评分点。 |",
        f"| ambiguous | {counts['ambiguous']} | 题目或预期过于模糊，当前不宜计分。 |",
        f"| metric_scoreable | {counts['metric_scoreable']} | 性能指标题，应按时延/稳定性评分。 |",
        f"| operation_scoreable | {counts['operation_scoreable']} | 产品操作题，按操作结果和证据评分。 |",
        f"| not_scoreable | {counts['not_scoreable']} | 产品操作或元用例，不进入模型文本评分。 |",
        "",
        "## 需要整改的题",
        "",
        "| ID | 类别 | 模块 | 能力 | 摘要 | 当前预期 | 问题 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["answerability"] in {"rubric_needed", "ambiguous"}:
            lines.append(
                f"| {row['case_id']} | {row['answerability']} | {md_cell(row['module'], 24)} | "
                f"{md_cell(row['feature'], 24)} | {md_cell(row['summary'], 52)} | "
                f"{md_cell(row['expected'], 70)} | {md_cell(row['reason'], 70)} |"
            )

    lines.extend(
        [
            "",
            "## 全量明细",
            "",
            "| ID | 类别 | 模块 | 能力 | 当前预期 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['answerability']} | {md_cell(row['module'], 24)} | "
            f"{md_cell(row['feature'], 24)} | {md_cell(row['expected'], 90)} |"
        )
    (args.out_dir / "answerability_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_dir / "answerability_audit.md")
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
