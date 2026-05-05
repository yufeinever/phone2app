from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def text(value: Any) -> str:
    return str(value or "").strip()


def load_results(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        path = path / "cases.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("results", payload) if isinstance(payload, dict) else payload


def actual_text(result: dict[str, Any]) -> str:
    turns = result.get("turns") or []
    values = [text(turn.get("actual")) for turn in turns if text(turn.get("actual"))]
    return "\n".join(values) if values else text(result.get("actual"))


def classify(result: dict[str, Any], max_capture_chars: int) -> tuple[str, str]:
    actual = actual_text(result)
    status = text(result.get("status"))
    if status in {"error", "fail"} and not actual:
        return "no_answer", "执行失败且没有抓到回答。"
    if not actual:
        return "no_answer", "actual 为空。"
    if actual in {"正在分析用户意图...", "正在分析用户意图…", "思考中", "生成中"}:
        return "intermediate_state", "抓到的是生成/分析中间态，不是最终回答。"
    if len(actual) >= max_capture_chars:
        return "possible_truncated", f"长度达到或接近抓取上限 {max_capture_chars}，可能被截断。"
    if actual.endswith(("：", "，", "、", "（", "(", "；", ";")):
        return "possible_truncated", "回答以非终止标点结尾，可能只抓到半截。"
    if re.search(r"(\.\.\.|…)$", actual):
        return "possible_truncated", "回答末尾是省略号，可能被界面或脚本截断。"
    if 0 < len(actual) < 8:
        return "very_short", "回答极短；客观题可能正常，开放题需复核。"
    return "ok_or_unknown", "未发现明显截断特征；仍不代表滚动长回答已完整。"


def md_cell(value: Any, limit: int = 100) -> str:
    value = re.sub(r"\s+", " ", text(value)).replace("|", "\\|")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def parse_run(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--run 格式必须是 产品名=报告目录或cases.json")
    name, raw_path = value.split("=", 1)
    return name.strip(), Path(raw_path.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计 App 回答抓取是否可能不完整")
    parser.add_argument("--run", action="append", type=parse_run, required=True, help="产品名=报告目录或cases.json")
    parser.add_argument("--case-source", type=Path, default=None, help="可选；只审计该用例文件中的 case_id")
    parser.add_argument("--out-dir", type=Path, default=Path("reports/compare_eval/response-capture-completeness-audit"))
    parser.add_argument("--max-capture-chars", type=int, default=2000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wanted_ids = None
    if args.case_source:
        wanted_payload = json.loads(args.case_source.read_text(encoding="utf-8"))
        wanted_rows = wanted_payload.get("results", wanted_payload) if isinstance(wanted_payload, dict) else wanted_payload
        wanted_ids = {text(row.get("case_id") or row.get("id")) for row in wanted_rows}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    summary = {}
    for product, path in args.run:
        product_rows = []
        for result in load_results(path):
            if wanted_ids is not None and text(result.get("case_id")) not in wanted_ids:
                continue
            category, reason = classify(result, args.max_capture_chars)
            row = {
                "product": product,
                "case_id": result.get("case_id"),
                "status": result.get("status"),
                "category": category,
                "reason": reason,
                "actual_len": len(actual_text(result)),
                "actual_tail": actual_text(result)[-80:],
                "summary": result.get("summary"),
            }
            rows.append(row)
            product_rows.append(row)
        summary[product] = dict(Counter(row["category"] for row in product_rows))

    payload = {
        "metadata": {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "note": "该审计只能发现明显风险；ok_or_unknown 不等于已证明长回答完整。",
        },
        "summary": summary,
        "results": rows,
    }
    (args.out_dir / "capture_completeness_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 回答抓取完整性审计",
        "",
        f"- 创建时间：{payload['metadata']['created_at']}",
        "- 说明：`ok_or_unknown` 只表示未命中明显截断特征，不代表长回答已通过滚动完整采集。",
        "",
        "## 统计",
        "",
        "| 产品 | ok_or_unknown | very_short | possible_truncated | intermediate_state | no_answer |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for product, counts in summary.items():
        lines.append(
            f"| {product} | {counts.get('ok_or_unknown', 0)} | {counts.get('very_short', 0)} | "
            f"{counts.get('possible_truncated', 0)} | {counts.get('intermediate_state', 0)} | {counts.get('no_answer', 0)} |"
        )
    lines.extend(
        [
            "",
            "## 风险样本",
            "",
            "| 产品 | Case | 类别 | 长度 | 摘要 | 尾部片段 | 原因 |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for row in rows:
        if row["category"] in {"possible_truncated", "intermediate_state", "no_answer"}:
            lines.append(
                f"| {row['product']} | {row['case_id']} | {row['category']} | {row['actual_len']} | "
                f"{md_cell(row['summary'], 50)} | {md_cell(row['actual_tail'], 80)} | {md_cell(row['reason'], 80)} |"
            )
    (args.out_dir / "capture_completeness_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(args.out_dir / "capture_completeness_audit.md")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
