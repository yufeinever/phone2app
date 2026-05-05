from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_300 = ROOT / "reports" / "product_eval" / "main_dialogue_case_matrix_full_300_20260504.md"
EXTERNAL_JSON = ROOT / "reports" / "product_eval" / "main_dialogue_external_empirical_wrong_50_20260504.json"
OUT = ROOT / "reports" / "product_eval" / "main_dialogue_case_matrix_full_350_20260504.md"


def clean(value: Any) -> str:
    return str(value or "").replace("|", "；").replace("\r", " ").replace("\n", " ").strip()


def main() -> int:
    base = BASE_300.read_text(encoding="utf-8").rstrip()
    base = re.sub(r"\n## 外部实测错题扩展区[\s\S]*$", "", base).rstrip()
    external = json.loads(EXTERNAL_JSON.read_text(encoding="utf-8"))
    if len(external) != 50:
        raise SystemExit(f"外部错题数量错误：{len(external)}，期望 50")

    existing_ids = set(re.findall(r"^\| (MD-[^| ]+)", base, flags=re.MULTILINE))
    rows: list[str] = []
    for index, case in enumerate(external, start=1):
        case_id = f"MD-EXT-BBM-{index:03d}"
        if case_id in existing_ids:
            raise SystemExit(f"重复 ID：{case_id}")
        expected = (
            f"标准答案 {case['target']}；外部源模型 {case['source_model']} 曾错误回答 "
            f"{case['source_model_wrong_answer']}；错误步骤 index={case['mistake_index_0_based']}"
        )
        source = f"BIG-Bench Mistake/{case['source_file']}:{case['source_line']}"
        trap = f"external_empirical；{case['task']}；PaLM2L_wrong"
        row = [
            case_id,
            "P1",
            "外部实测错题",
            case["ability"],
            source,
            "是",
            trap,
            case["test_prompt"],
            expected,
            "待执行",
            "待执行",
            "待执行",
            "待执行",
        ]
        rows.append("| " + " | ".join(clean(item) for item in row) + " |")

    content = (
        base
        + "\n\n## 外部实测错题扩展区\n\n"
        + "说明：本节追加 50 道外部高级模型真实答错样本，来源为 BIG-Bench Mistake。每条均满足 `source_model_answer != target` 且 `mistake_index` 非空。原始 CoT、源模型错误答案、标准答案和回链保存在 `main_dialogue_external_empirical_wrong_50_20260504.json`。\n\n"
        + "| ID | 优先级 | 模块 | 子能力 | 参考/来源 | 易错 | 陷阱类型 | 题目/操作摘要 | 预期回答/判分规则 | App 实际回答 | 响应时间 | 结果 | 证据路径 |\n"
        + "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        + "\n".join(rows)
        + "\n"
    )
    total = len(re.findall(r"^\| MD-", content, flags=re.MULTILINE))
    if total != 350:
        raise SystemExit(f"总题数错误：{total}，期望 350")

    OUT.write_text(content, encoding="utf-8")
    print(f"wrote={OUT}")
    print("base_rows=300 added_external=50 total_rows=350")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
