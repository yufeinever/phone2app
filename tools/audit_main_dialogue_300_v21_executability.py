from __future__ import annotations

import json
import argparse
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.1-20260505" / "cases.json"
DEFAULT_OUT_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-300-v2.1-executability-audit-20260505"


MATERIAL_TASK_WORDS = [
    "翻译",
    "阅读",
    "摘要",
    "压缩",
    "改写",
    "抽取",
    "提取",
    "整理",
    "补全",
    "解释这段",
    "根据表格",
    "根据文本",
    "从文本",
    "从短文",
    "投诉内容",
    "会议纪要",
    "JSON",
    "材料",
    "短文",
    "文本",
]

MATERIAL_MARKERS = [
    "材料：",
    "短文：",
    "文本：",
    "表格：",
    "原句：",
    "句子：",
    "投诉内容：",
    "投诉文本：",
    "会议记录：",
    "会议纪要",
    "JSON：",
    "需求1：",
    "代码",
    "`",
    "{",
    "：",
]

PLACEHOLDER_PATTERNS = [
    r"翻译一段话",
    r"翻译.*一篇文章",
    r"阅读.*材料.*请",
    r"根据(上文|上述|前文)",
    r"从(下面|以下)?(文本|短文|材料)中",
    r"请提供",
    r"补充具体",
    r"没有提供",
    r"后续产品操作生成一段短回答",
    r"为后续产品操作生成",
]


def text(value: Any) -> str:
    return str(value or "").strip()


def all_inputs(case: dict[str, Any]) -> list[str]:
    return [text(turn.get("input")) for turn in case.get("turns", []) if text(turn.get("input"))]


def has_material(prompt: str) -> bool:
    if any(marker in prompt for marker in MATERIAL_MARKERS):
        return True
    # English/code snippets and structured examples often include enough material without Chinese markers.
    if re.search(r"[A-Za-z_]+\\([^)]*\\)|return\\s+|SELECT\\s+|def\\s+", prompt):
        return True
    return False


def classify(case: dict[str, Any]) -> tuple[str, str]:
    mode = text(case.get("execution_mode"))
    test_type = text(case.get("test_type"))
    inputs = all_inputs(case)
    prompt = "\n".join(inputs)
    summary = text(case.get("summary"))

    if mode == "skip" or test_type == "metadata_only":
        return "not_executable", "元用例，不应执行。"
    if not inputs:
        return "not_executable", "没有 turns.input。"
    if any(re.search(pattern, prompt) for pattern in PLACEHOLDER_PATTERNS):
        if test_type == "product_operation":
            return "operation_seed_only", "这是产品操作前置 seed，不是模型能力题；需要 operation_steps 才完整。"
        return "incomplete", "输入看起来仍是占位/要求补材料。"

    material_task = any(word in summary + prompt for word in MATERIAL_TASK_WORDS)
    if material_task and not has_material(prompt):
        return "incomplete", "任务需要材料/文本/句子/表格，但 prompt 中未发现明确材料。"

    if test_type == "product_operation" or mode == "uiautomator2_operation":
        steps = case.get("operation_steps") or []
        if not steps:
            return "incomplete_operation", "产品操作题缺少 operation_steps。"
        return "operation_executable", "产品操作题具备 seed prompt 和 operation_steps。"

    if mode == "uiautomator2_text_dialogue_with_metrics":
        return "metric_executable", "可执行，但结果应按指标评价。"

    return "dialogue_executable", "输入自包含，可由人类理解并直接发送。"


def md_cell(value: Any, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", text(value)).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计主对话题库输入是否自包含、可执行")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.source
    out_dir = args.out_dir
    cases = json.loads(source.read_text(encoding="utf-8"))["results"]
    rows = []
    for case in cases:
        status, reason = classify(case)
        rows.append(
            {
                "case_id": case["case_id"],
                "test_type": case.get("test_type"),
                "execution_mode": case.get("execution_mode"),
                "summary": case.get("summary"),
                "inputs": all_inputs(case),
                "executability": status,
                "reason": reason,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {"created_at": datetime.now().isoformat(timespec="seconds"), "source": str(source)},
        "counts": Counter(row["executability"] for row in rows),
        "results": rows,
    }
    (out_dir / "executability_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = Counter(row["executability"] for row in rows)
    lines = [
        "# 主对话 300-v2.1 可执行性审计",
        "",
        f"- 创建时间：{payload['metadata']['created_at']}",
        f"- 源文件：`{source}`",
        "",
        "## 统计",
        "",
        "| 类别 | 数量 | 含义 |",
        "| --- | ---: | --- |",
    ]
    for key, meaning in [
        ("dialogue_executable", "纯文本对话题，输入自包含。"),
        ("operation_executable", "产品操作题，具备 seed prompt 和 operation_steps。"),
        ("metric_executable", "可执行，但应按时延/性能指标评价。"),
        ("operation_seed_only", "只有产品操作 seed，不应当成模型能力题。"),
        ("incomplete", "缺材料或仍有占位式输入。"),
        ("incomplete_operation", "产品操作题缺少操作步骤。"),
        ("not_executable", "元用例或无输入，不应执行。"),
    ]:
        lines.append(f"| {key} | {counts[key]} | {meaning} |")

    lines.extend(
        [
            "",
            "## 需要处理的问题题",
            "",
            "| ID | 类别 | 摘要 | 输入片段 | 问题 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        if row["executability"] in {"incomplete", "incomplete_operation", "not_executable", "operation_seed_only"}:
            lines.append(
                f"| {row['case_id']} | {row['executability']} | {md_cell(row['summary'], 50)} | "
                f"{md_cell(' / '.join(row['inputs']), 90)} | {md_cell(row['reason'], 80)} |"
            )

    lines.extend(
        [
            "",
            "## 全量明细",
            "",
            "| ID | 类别 | 摘要 | 输入片段 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['executability']} | {md_cell(row['summary'], 50)} | {md_cell(' / '.join(row['inputs']), 120)} |"
        )

    (out_dir / "executability_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out_dir / "executability_audit.md")
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
