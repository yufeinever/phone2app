from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = Path(os.environ.get("TEMP", ".")) / "big-bench-mistake"
OUT_DIR = ROOT / "reports" / "product_eval"
OUT_MD = OUT_DIR / "main_dialogue_external_empirical_wrong_50_20260504.md"
OUT_JSON = OUT_DIR / "main_dialogue_external_empirical_wrong_50_20260504.json"

TASKS = [
    ("logical_deduction", "logical_deduction.jsonl", 10, "逻辑演绎/选项推理"),
    ("tracking_shuffled_objects", "tracking_shuffled_objects.jsonl", 10, "对象追踪/状态更新"),
    ("multistep_arithmetic", "multistep_arithmetic.jsonl", 10, "多步算术"),
    ("word_sorting", "word_sorting.jsonl", 10, "英文单词排序"),
    ("dyck_languages", "dyck_languages.jsonl", 10, "括号/Dyck 语言补全"),
]


def md_cell(value: Any, limit: int = 160) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def prompt_for(task: str, source_input: str) -> str:
    if task == "multistep_arithmetic":
        return f"请计算下面表达式，只输出最终数值：{source_input}"
    if task == "word_sorting":
        return f"请把下面题目中的英文单词按字母序排序，只输出排序结果：{source_input}"
    if task == "dyck_languages":
        return f"请补全下面括号序列，使其成为合法的 Dyck 括号语言，只输出需要补全的括号：{source_input}"
    if task == "tracking_shuffled_objects":
        return "请解答下面对象交换/追踪题，只输出正确选项：\n" + source_input
    return "请解答下面逻辑演绎选择题，只输出正确选项：\n" + source_input


def pick_cases() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task, filename, limit, zh_type in TASKS:
        picked = 0
        path = SRC / filename
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            row = json.loads(line)
            answer = str(row.get("answer", "")).strip()
            target = str(row.get("target", "")).strip()
            if answer == target or row.get("mistake_index") is None:
                continue
            picked += 1
            out.append(
                {
                    "id": f"EXT-BBM-{len(out) + 1:03d}",
                    "source_dataset": "BIG-Bench Mistake",
                    "source_url": f"https://github.com/WHGTyen/BIG-Bench-Mistake/blob/main/{filename}",
                    "source_file": filename,
                    "source_line": line_no,
                    "task": task,
                    "ability": zh_type,
                    "source_model": "PaLM 2-L (Unicorn)",
                    "empirical_evidence": "source_model_answer != target and mistake_index is not null",
                    "mistake_index_0_based": row.get("mistake_index"),
                    "source_model_wrong_answer": answer,
                    "target": target,
                    "test_prompt": prompt_for(task, row["input"]),
                    "source_input": row["input"],
                    "source_steps": row.get("steps", []),
                }
            )
            if picked >= limit:
                break
        if picked != limit:
            raise RuntimeError(f"{task} only picked {picked}, expected {limit}")
    return out


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"BIG-Bench Mistake clone not found: {SRC}")
    cases = pick_cases()
    if len(cases) != 50:
        raise SystemExit(f"expected 50 cases, got {len(cases)}")

    OUT_JSON.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 外部实测错题池 50 题",
        "",
        "## 来源说明",
        "",
        "- 来源：BIG-Bench Mistake，Apache-2.0 license。",
        "- 论文：LLMs cannot find reasoning errors, but can correct them given the error location，ACL 2024 Findings。",
        "- 错误证据：每条均满足 `PaLM 2-L (Unicorn) answer != target` 且 `mistake_index` 非空。",
        "- 注意：这 50 条是外部高级模型的真实错误样本；不是我按题型猜测的易错题。",
        "- Markdown 表只展示可读摘要；完整原始输入、模型错误 CoT、标准答案和错误位置保存在同名 JSON。",
        "",
        "## 分布",
        "",
        "| 任务 | 数量 | 能力点 |",
        "| --- | ---: | --- |",
    ]
    for task, _, limit, zh_type in TASKS:
        lines.append(f"| {task} | {limit} | {zh_type} |")

    lines.extend(
        [
            "",
            "## 50 题清单",
            "",
            "| ID | 任务 | 能力点 | 来源行 | 源模型 | 错误位置 | 标准答案 | 源模型错误答案 | 测试输入摘要 |",
            "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- |",
        ]
    )
    for case in cases:
        lines.append(
            f"| {case['id']} | {case['task']} | {case['ability']} | {case['source_line']} | "
            f"{case['source_model']} | {case['mistake_index_0_based']} | {md_cell(case['target'], 80)} | "
            f"{md_cell(case['source_model_wrong_answer'], 80)} | {md_cell(case['test_prompt'], 180)} |"
        )
    lines.extend(
        [
            "",
            "## 后续接入建议",
            "",
            "- 先作为 `external_empirical` 题池，不直接替换现有 300 题。",
            "- 对逻辑演绎和对象追踪题，后续可以翻译为中文并保留 `source_file/source_line` 回链。",
            "- 执行时应记录灵犀答案，并新增字段 `lingxi_vs_external_model`，区分“灵犀也错”和“灵犀修复了外部模型错误”。",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote_md={OUT_MD}")
    print(f"wrote_json={OUT_JSON}")
    print("cases=50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
