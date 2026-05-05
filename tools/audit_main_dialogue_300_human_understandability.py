from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.2-20260505" / "cases.json"
DEFAULT_OUT_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.2-human-understandability-audit-20260505"


MATERIAL_TASK_RE = re.compile(
    r"翻译|摘要|总结|提炼|压缩|提取|抽取|改写|阅读|主旨|整理|补全|转换|转成|生成安抚回复"
)
MATERIAL_MARKER_RE = re.compile(
    r"材料[:：]|短文[:：]|文本[:：]|原句[:：]|句子[:：]|投诉(?:文本|内容)?[:：]|"
    r"表格[:：]|JSON[:：]|需求[:：]|会议记录[:：]|用户说[:：]|信息[:：]|模板[:：]|"
    r"文言文[:：]|`[^`]+`|“[^”]+”|：[^。]{4,}"
)

META_SUMMARY_RE = re.compile(
    r"^(问今天|要求逐字|忽略规则|假装没有限制|用 Base64|根据姓名城市猜|要求代替用户)"
)
UNDERSPECIFIED_RE = re.compile(
    r"在 A/B/C 中选择，不解释|只列 4 条建议。请直接回答。$|"
    r"用“结论/理由/下一步”三行回答。请直接回答。$"
)


def text(value: Any) -> str:
    return str(value or "").strip()


def all_inputs(case: dict[str, Any]) -> list[str]:
    return [text(turn.get("input")) for turn in case.get("turns", []) if text(turn.get("input"))]


def md_cell(value: Any, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", text(value)).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def classify(case: dict[str, Any]) -> tuple[str, str]:
    mode = text(case.get("execution_mode"))
    test_type = text(case.get("test_type"))
    prompt = " / ".join(all_inputs(case))
    summary = text(case.get("summary"))

    if mode == "skip" or test_type == "metadata_only":
        return "not_executable", "元用例，不应发送给 App。"
    if not prompt:
        return "not_executable", "没有可发送的 turns.input。"

    if MATERIAL_TASK_RE.search(prompt) and not MATERIAL_MARKER_RE.search(prompt):
        return "missing_material_or_object", "任务需要原文/材料/句子/表格，但 prompt 未提供明确对象。"

    if META_SUMMARY_RE.search(prompt):
        return "meta_summary_as_prompt", "prompt 像内部测试摘要，不像真实用户会发送的问题。"

    if UNDERSPECIFIED_RE.search(prompt):
        return "underspecified_prompt", "题干缺少任务对象或选项，人类无法判断该回答什么。"

    if case.get("case_id") == "MD-EX-S16" and "作品：" not in prompt and "《" not in prompt:
        return "ambiguous_safety_object", "版权安全题没有给出文章名或片段，仍能测试拒答，但不适合作为清晰主对话题。"

    if test_type == "product_operation" or mode == "uiautomator2_operation":
        return "operation_understandable", "产品操作题具备 seed prompt，需结合 operation_steps 执行。"

    if mode == "uiautomator2_text_dialogue_with_metrics":
        return "metric_understandable", "可作为时延/性能指标题执行。"

    return "dialogue_understandable", "题干自包含，人类可直接理解并发送。"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计主对话题库是否人类可理解、可直接发送")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = json.loads(args.source.read_text(encoding="utf-8"))["results"]
    rows = []
    for case in cases:
        category, reason = classify(case)
        rows.append(
            {
                "case_id": case["case_id"],
                "summary": case.get("summary"),
                "execution_mode": case.get("execution_mode"),
                "test_type": case.get("test_type"),
                "inputs": all_inputs(case),
                "understandability": category,
                "reason": reason,
            }
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    counts = Counter(row["understandability"] for row in rows)
    payload = {
        "metadata": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str(args.source),
        },
        "counts": counts,
        "results": rows,
    }
    (args.out_dir / "understandability_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 主对话 300-v2.2 人类可理解性审计",
        "",
        f"- 创建时间：{payload['metadata']['created_at']}",
        f"- 源文件：`{args.source}`",
        "",
        "## 统计",
        "",
        "| 类别 | 数量 | 含义 |",
        "| --- | ---: | --- |",
        f"| dialogue_understandable | {counts['dialogue_understandable']} | 纯文本题，题干自包含。 |",
        f"| operation_understandable | {counts['operation_understandable']} | 产品操作题，需结合 operation_steps。 |",
        f"| metric_understandable | {counts['metric_understandable']} | 可作为时延/性能指标题。 |",
        f"| missing_material_or_object | {counts['missing_material_or_object']} | 缺原文、材料、句子、表格或任务对象。 |",
        f"| meta_summary_as_prompt | {counts['meta_summary_as_prompt']} | 把内部测试摘要当成了用户 prompt。 |",
        f"| underspecified_prompt | {counts['underspecified_prompt']} | 题干缺少任务对象或选项。 |",
        f"| ambiguous_safety_object | {counts['ambiguous_safety_object']} | 安全题对象不清晰。 |",
        f"| not_executable | {counts['not_executable']} | 元用例或没有输入。 |",
        "",
        "## 需要整改的题",
        "",
        "| ID | 类别 | 摘要 | 输入片段 | 问题 |",
        "| --- | --- | --- | --- | --- |",
    ]
    bad_categories = {
        "missing_material_or_object",
        "meta_summary_as_prompt",
        "underspecified_prompt",
        "ambiguous_safety_object",
        "not_executable",
    }
    for row in rows:
        if row["understandability"] in bad_categories:
            lines.append(
                f"| {row['case_id']} | {row['understandability']} | {md_cell(row['summary'], 48)} | "
                f"{md_cell(' / '.join(row['inputs']), 110)} | {md_cell(row['reason'], 90)} |"
            )

    (args.out_dir / "understandability_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_dir / "understandability_audit.md")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
