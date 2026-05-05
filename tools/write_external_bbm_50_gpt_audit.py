from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "product_eval" / "main-dialogue-external-bbm-50-20260504-105026"
EXTERNAL = ROOT / "reports" / "product_eval" / "main_dialogue_external_empirical_wrong_50_20260504.json"


VERDICTS: dict[str, tuple[str, str]] = {
    "MD-EXT-BBM-001": ("wrong", "目标 (E)，实际 (D)。"),
    "MD-EXT-BBM-002": ("wrong", "目标 (A)，实际 (B)。"),
    "MD-EXT-BBM-003": ("wrong", "目标 (G)，实际 (B)。"),
    "MD-EXT-BBM-004": ("correct", "目标 (D)，实际以 (D) 作答。"),
    "MD-EXT-BBM-005": ("wrong", "目标 (B)，实际 (G)。"),
    "MD-EXT-BBM-006": ("wrong", "目标 (A)，实际 (G)。"),
    "MD-EXT-BBM-007": ("wrong", "目标 (C)，实际 (E)。"),
    "MD-EXT-BBM-008": ("correct", "目标 (F)，实际以 (F) 作答。"),
    "MD-EXT-BBM-009": ("correct", "目标 (B)，实际为 (B)，自动 fail 属误伤。"),
    "MD-EXT-BBM-010": ("correct", "目标 (D)，实际以 (D) 作答。"),
    "MD-EXT-BBM-011": ("wrong", "目标 (B)，实际 (A)。"),
    "MD-EXT-BBM-012": ("correct", "目标 (A)，实际以 (A) 作答。"),
    "MD-EXT-BBM-013": ("correct", "目标 (B)，实际最终 boxed B。"),
    "MD-EXT-BBM-014": ("correct", "目标 (B)，实际以 (B) 作答。"),
    "MD-EXT-BBM-015": ("wrong", "目标 (A)，实际 (B)。"),
    "MD-EXT-BBM-016": ("wrong", "目标 (B)，实际 (A)。"),
    "MD-EXT-BBM-017": ("correct", "目标 (B)，实际以 (B) 作答。"),
    "MD-EXT-BBM-018": ("wrong", "目标 (C)，实际 (D)。"),
    "MD-EXT-BBM-019": ("wrong", "目标 (B)，实际 (D)。"),
    "MD-EXT-BBM-020": ("wrong", "目标 (C)，实际 (A)。"),
    "MD-EXT-BBM-021": ("capture_issue_rerun", "UI/XML 抓取未捕获模型最终数值，只抓到题干和首页控件，需重跑。"),
    "MD-EXT-BBM-022": ("wrong", "目标 13，实际 11。"),
    "MD-EXT-BBM-023": ("wrong", "目标 -8，实际 -28。"),
    "MD-EXT-BBM-024": ("wrong", "目标 -308，实际 -274。"),
    "MD-EXT-BBM-025": ("correct", "目标 378，实际最终 boxed 378。"),
    "MD-EXT-BBM-026": ("correct", "目标 -57，实际最终 boxed -57。"),
    "MD-EXT-BBM-027": ("wrong", "目标 -7，实际 0。"),
    "MD-EXT-BBM-028": ("wrong", "目标 324，实际 -411。"),
    "MD-EXT-BBM-029": ("wrong", "目标 0，实际 -10。"),
    "MD-EXT-BBM-030": ("wrong", "目标 -14，实际 -12。"),
    "MD-EXT-BBM-031": ("wrong", "目标排序包含 cider 且位置不同，实际缺 cider 并顺序错误。"),
    "MD-EXT-BBM-032": ("wrong", "实际缺 btl，且 cargoes 被输出为 cargoses。"),
    "MD-EXT-BBM-033": ("wrong", "collateral/collocate 和 tattoo/tempestuous 顺序错误。"),
    "MD-EXT-BBM-034": ("correct", "英文单词排序与目标一致。"),
    "MD-EXT-BBM-035": ("wrong", "distinct 被放到末尾，多个词序不符。"),
    "MD-EXT-BBM-036": ("correct", "英文单词排序与目标一致。"),
    "MD-EXT-BBM-037": ("wrong", "collocate/collateral 顺序错误。"),
    "MD-EXT-BBM-038": ("wrong", "存在拼写变形、缺词和顺序错误。"),
    "MD-EXT-BBM-039": ("correct", "英文单词排序与目标一致。"),
    "MD-EXT-BBM-040": ("correct", "英文单词排序与目标一致。"),
    "MD-EXT-BBM-041": ("wrong", "目标 ] }，实际 } ]，顺序反了。"),
    "MD-EXT-BBM-042": ("wrong", "目标 > >，实际最终 ] > }。"),
    "MD-EXT-BBM-043": ("wrong", "目标 ] ) )，实际 ) )，缺少 ]。"),
    "MD-EXT-BBM-044": ("wrong", "目标 ] ] ]，实际 ] ]，缺少一个 ]。"),
    "MD-EXT-BBM-045": ("capture_issue_rerun", "UI/XML 抓取到长推理中段后被截断，没有最终补全答案，需重跑并限制只输出答案。"),
    "MD-EXT-BBM-046": ("correct", "目标 ) ]，实际 ) ]，自动 fail 属误伤。"),
    "MD-EXT-BBM-047": ("wrong", "目标 ) } >，实际 )}，缺少 >。"),
    "MD-EXT-BBM-048": ("wrong", "目标 > } ]，实际 ] }，顺序和缺项不符。"),
    "MD-EXT-BBM-049": ("wrong", "目标 ]，实际 }。"),
    "MD-EXT-BBM-050": ("wrong", "目标 ]，实际 < >。"),
}


def md_cell(value: Any, limit: int = 140) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def main() -> int:
    results = json.loads((RUN / "cases.json").read_text(encoding="utf-8"))["results"]
    external = json.loads(EXTERNAL.read_text(encoding="utf-8"))
    source_by_id = {f"MD-EXT-BBM-{i:03d}": item for i, item in enumerate(external, start=1)}
    audited = []
    for result in results:
        case_id = result["case_id"]
        verdict, note = VERDICTS[case_id]
        source = source_by_id[case_id]
        audited.append(
            {
                "case_id": case_id,
                "task": source["task"],
                "target": source["target"],
                "lingxi_actual": result.get("actual", ""),
                "external_wrong_answer": source["source_model_wrong_answer"],
                "auto_status": result["status"],
                "gpt_audit_status": verdict,
                "gpt_audit_note": note,
                "response_screenshot": result.get("response_screenshot"),
                "complete_ms": result.get("response_complete_time_ms"),
            }
        )

    counts = Counter(item["gpt_audit_status"] for item in audited)
    by_task: dict[str, Counter[str]] = {}
    for item in audited:
        by_task.setdefault(item["task"], Counter())[item["gpt_audit_status"]] += 1

    lines = [
        "# GPT 人工复核：外部实测错题 50 题",
        "",
        "## 复核口径",
        "",
        "- 选择题：必须与 BIG-Bench Mistake 标准选项一致。",
        "- 多步算术：最终数值必须一致。",
        "- 英文排序：词项完整且顺序一致才算正确。",
        "- Dyck 括号补全：补全符号序列必须一致。",
        "- UI 抓取未捕获最终答案或长回答被截断时，标记为 `capture_issue_rerun`，不计入模型真实对错。",
        "",
        "## 总体结论",
        "",
        "| 状态 | 数量 |",
        "| --- | ---: |",
        f"| correct | {counts.get('correct', 0)} |",
        f"| wrong | {counts.get('wrong', 0)} |",
        f"| capture_issue_rerun | {counts.get('capture_issue_rerun', 0)} |",
        "",
        "## 分任务统计",
        "",
        "| 任务 | correct | wrong | capture_issue_rerun |",
        "| --- | ---: | ---: | ---: |",
    ]
    for task, counter in by_task.items():
        lines.append(
            f"| {task} | {counter.get('correct', 0)} | {counter.get('wrong', 0)} | {counter.get('capture_issue_rerun', 0)} |"
        )

    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| ID | 任务 | 标准答案 | 灵犀实际答案 | 外部模型错误答案 | 自动状态 | GPT复核 | 说明 | 截图 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in audited:
        lines.append(
            f"| {item['case_id']} | {item['task']} | {md_cell(item['target'], 70)} | "
            f"{md_cell(item['lingxi_actual'], 120)} | {md_cell(item['external_wrong_answer'], 70)} | "
            f"{item['auto_status']} | {item['gpt_audit_status']} | {md_cell(item['gpt_audit_note'], 120)} | "
            f"{md_cell(item['response_screenshot'], 80)} |"
        )

    (RUN / "external_bbm_50_gpt_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RUN / "external_bbm_50_gpt_audit.json").write_text(
        json.dumps({"counts": dict(counts), "by_task": {k: dict(v) for k, v in by_task.items()}, "results": audited}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
