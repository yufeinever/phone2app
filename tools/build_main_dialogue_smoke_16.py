from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "product_eval" / "main-dialogue-300-v3.2-20260505" / "dialogue_cases.json"
OUT_DIR = ROOT / "reports" / "product_eval" / "main-dialogue-smoke-16-20260505"


PICKS = [
    ("逻辑推理", "MD-X01"),
    ("逻辑推理", "MD-X13"),
    ("数学推理", "MD-Q02"),
    ("数学推理", "MD-Q08"),
    ("中文语言", "MD-W01"),
    ("中文语言", "MD-EX-Z02"),
    ("指令遵循", "MD-I01"),
    ("指令遵循", "MD-I05"),
    ("上下文多轮", "MD-F05"),
    ("上下文多轮", "MD-EX-C05"),
    ("代码能力", "MD-C01"),
    ("代码能力", "MD-EX-P05"),
    ("事实常识", "MD-K01"),
    ("事实常识", "MD-T03"),
    ("安全红队", "MD-X24"),
    ("安全红队", "MD-S12"),
]


def md_cell(value: Any, limit: int = 120) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|").strip()
    return text if len(text) <= limit else text[: limit - 1] + "..."


def main() -> int:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    all_cases = payload["results"]
    by_id = {case["case_id"]: case for case in all_cases}
    missing = [case_id for _group, case_id in PICKS if case_id not in by_id]
    if missing:
        raise RuntimeError(f"missing case ids: {missing}")

    cases = []
    for smoke_group, case_id in PICKS:
        case = dict(by_id[case_id])
        case["smoke_group"] = smoke_group
        case["smoke_reason"] = "各主要能力类型抽样 2 题，组成约 15 题冒烟集合。"
        cases.append(case)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": "main-dialogue-smoke-16",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(SOURCE),
        "selection_policy": "8 个主要能力类型各选 2 题；只包含 send_as_model_question=true 的非产品操作用例。",
        "case_count": len(cases),
    }
    (OUT_DIR / "cases.json").write_text(
        json.dumps({"metadata": meta, "results": cases}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 主对话 Smoke 16 用例集",
        "",
        f"- 创建时间：{meta['created_at']}",
        f"- 来源：`{SOURCE}`",
        "- 选择策略：8 个主要能力类型各 2 题；不包含产品操作题。",
        "",
        "| 序号 | 类型 | 用例ID | 模块 | 能力 | 题目摘要 | 评分类型 |",
        "| ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for idx, case in enumerate(cases, 1):
        lines.append(
            f"| {idx} | {case['smoke_group']} | {case['case_id']} | {md_cell(case.get('module'), 30)} | "
            f"{md_cell(case.get('feature'), 30)} | {md_cell(case.get('summary'), 70)} | {case.get('scoring_type')} |"
        )
    (OUT_DIR / "case_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_DIR / "cases.json")
    print(OUT_DIR / "case_overview.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
