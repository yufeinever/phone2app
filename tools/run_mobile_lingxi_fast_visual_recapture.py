from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import uiautomator2 as u2

from mobile_lingxi_common import (
    PACKAGE,
    SERIAL,
    adb,
    adb_no_raise,
    dump_xml,
    find_input,
    find_send,
    force_stop_app,
    foreground_summary,
    launch_app,
    open_new_chat,
    page_text,
    recover_to_text_chat,
    screencap,
    tap_node,
)
from run_mobile_lingxi_eval import app_version, load_cases
from run_mobile_lingxi_recapture_eval import (
    DEFAULT_CASE_SOURCE,
    DEFAULT_REVIEW_SOURCE,
    DEFAULT_THIRD_REVIEW_SOURCE,
    extract_answer,
    load_mobile_product_issue_ids,
)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def set_fast_input() -> Any:
    device = u2.connect_usb(SERIAL)
    try:
        device.set_input_ime(True)
    except Exception:
        device.set_fastinput_ime(True)
    return device


def type_text(device: Any, text: str) -> float:
    start = time.perf_counter()
    try:
        device.send_keys(text, clear=True)
    except Exception:
        device.send_keys(text, clear=False)
    return (time.perf_counter() - start) * 1000


def snapshot(case_dir: Path, prefix: str) -> tuple[Path, Path, list[Any], str]:
    png = case_dir / f"{prefix}.png"
    xml = case_dir / f"{prefix}.xml"
    screencap(png)
    nodes = dump_xml(xml)
    visible = page_text(nodes)
    (case_dir / f"{prefix}.visible.txt").write_text(visible, encoding="utf-8")
    return png, xml, nodes, visible


def select_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.case_ids:
        wanted = [part.strip() for part in args.case_ids.split(",") if part.strip()]
    else:
        wanted = load_mobile_product_issue_ids(args.review_source, args.third_review_source, args.include_format)
    if args.skip_done_from:
        done: set[str] = set()
        for source in args.skip_done_from:
            cases_path = source / "cases.json" if source.is_dir() else source
            if not cases_path.exists():
                continue
            raw = json.loads(cases_path.read_text(encoding="utf-8"))
            for row in raw.get("results", []) if isinstance(raw, dict) else raw:
                if row.get("case_id"):
                    done.add(row["case_id"])
        wanted = [case_id for case_id in wanted if case_id not in done]
    if args.limit:
        wanted = wanted[: args.limit]
    by_id = {case["case_id"]: case for case in cases}
    missing = [case_id for case_id in wanted if case_id not in by_id]
    if missing:
        print(f"WARN missing case ids: {','.join(missing)}", flush=True)
    return [by_id[case_id] for case_id in wanted if case_id in by_id]


def classify_visual_hint(visible_text: str, extracted: str) -> str:
    text = "\n".join([visible_text or "", extracted or ""])
    if not text.strip():
        return "no_text_check_screenshot"
    if "表格" in text or "|" in text:
        return "visual_table_review"
    if "已更新至记忆库" in text or "记忆" in text:
        return "visual_memory_card_review"
    if "正在搜索" in text or "已联网搜索到" in text:
        return "visual_search_answer_review"
    if "想要我怎么称呼你" in text or "修改昵称" in text or "日程管理" in text:
        return "product_state_review"
    return "visual_answer_review"


def run_case(run_dir: Path, device: Any, case: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    case_id = case["case_id"]
    case_dir = run_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "case_id": case_id,
        "module": case.get("module", ""),
        "feature": case.get("feature", ""),
        "summary": case.get("summary", ""),
        "expected_result": case.get("expected_result", ""),
        "start_time": now(),
        "turns": [],
        "mode": "fast_visual_recapture",
    }
    try:
        open_new_chat(case_dir, f"{case_id}_new_chat")
        previous_visible = ""
        prompts: list[str] = []
        for idx, turn in enumerate(case["turns"], start=1):
            prefix = f"{case_id}_turn{idx}"
            nodes = recover_to_text_chat(case_dir, f"{prefix}_recover")
            edit = find_input(nodes)
            if not edit:
                raise RuntimeError("未找到移动灵犀输入框 id/et_input")
            before_png, before_xml, _before_nodes, before_text = snapshot(case_dir, f"{prefix}_before")
            tap_node(edit)
            input_ms = type_text(device, turn["input"])
            typed_png, typed_xml, typed_nodes, _typed_visible = snapshot(case_dir, f"{prefix}_typed")
            send = find_send(typed_nodes)
            if not send:
                raise RuntimeError("输入后未找到发送按钮 id/ll_txt_send")
            send_start = time.perf_counter()
            tap_node(send)
            send_ms = (time.perf_counter() - send_start) * 1000
            prompts.append(turn["input"])
            time.sleep(args.wait_s)
            response_png, response_xml, _response_nodes, response_visible = snapshot(case_dir, f"{prefix}_visual")
            extracted = extract_answer(previous_visible or before_text, response_visible, prompts)
            if args.extra_wait_s > 0:
                time.sleep(args.extra_wait_s)
                late_png, late_xml, _late_nodes, late_visible = snapshot(case_dir, f"{prefix}_visual_late")
            else:
                late_png, late_xml, late_visible = response_png, response_xml, response_visible
            late_extracted = extract_answer(previous_visible or before_text, late_visible, prompts)
            actual = late_extracted if len(late_extracted) >= len(extracted) else extracted
            visual_hint = classify_visual_hint(late_visible, actual)
            result["turns"].append(
                {
                    "turn_index": idx,
                    "input": turn["input"],
                    "expected": turn.get("expected", ""),
                    "actual_text_extract": actual,
                    "visual_hint": visual_hint,
                    "start_time": result["start_time"],
                    "end_time": now(),
                    "input_time_ms": round(input_ms, 1),
                    "send_tap_time_ms": round(send_ms, 1),
                    "wait_s": args.wait_s,
                    "extra_wait_s": args.extra_wait_s,
                    "before_screenshot": str(before_png),
                    "typed_screenshot": str(typed_png),
                    "response_screenshot": str(response_png),
                    "late_response_screenshot": str(late_png),
                    "before_xml": str(before_xml),
                    "typed_xml": str(typed_xml),
                    "response_xml": str(response_xml),
                    "late_response_xml": str(late_xml),
                    "response_visible_text": late_visible,
                }
            )
            previous_visible = late_visible
        result["status"] = "visual_review"
        result["visual_hint"] = result["turns"][-1]["visual_hint"] if result["turns"] else "no_turn"
    except Exception as exc:
        err_png = case_dir / f"{case_id}_error.png"
        err_xml = case_dir / f"{case_id}_error.xml"
        err_logcat = case_dir / f"{case_id}_error_logcat.txt"
        try:
            screencap(err_png)
            dump_xml(err_xml)
        except Exception:
            pass
        err_logcat.write_text(adb_no_raise(["logcat", "-d", "-t", "300"], timeout=20), encoding="utf-8")
        result["status"] = "error"
        result["visual_hint"] = "automation_error"
        result["error"] = str(exc)
        result["error_screenshot"] = str(err_png)
        result["error_xml"] = str(err_xml)
        result["error_logcat"] = str(err_logcat)
    result["end_time"] = now()
    result["duration_ms"] = round(
        (datetime.fromisoformat(result["end_time"]) - datetime.fromisoformat(result["start_time"])).total_seconds()
        * 1000,
        1,
    )
    return result


def write_reports(run_dir: Path, metadata: dict[str, Any], results: list[dict[str, Any]]) -> None:
    (run_dir / "cases.json").write_text(
        json.dumps({"metadata": metadata, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    counts = Counter(result.get("visual_hint", "unknown") for result in results)

    def cut(value: Any, size: int = 90) -> str:
        text = str(value or "").replace("|", "\\|").replace("\n", "<br>")
        return text[:size] + ("..." if len(text) > size else "")

    lines = [
        "# 移动灵犀快速视觉补测报告",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 开始时间：{metadata['start_time']}",
        f"- 更新时间：{metadata.get('updated_at', '')}",
        f"- App：`{metadata['app']}`",
        f"- App 版本：`{metadata['app_version']}`",
        f"- 已执行：{len(results)} / {metadata['selected_cases']}",
        f"- 等待策略：首图 `{metadata['wait_s']}s`，二次图 `{metadata['extra_wait_s']}s`",
        "",
        "## 视觉提示分类",
        "",
        "| 分类 | 数量 |",
        "|---|---:|",
    ]
    for key, count in counts.most_common():
        lines.append(f"| `{key}` | {count} |")
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| 用例 | 能力 | 摘要 | 视觉提示 | 文本抽取摘录 | 截图 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        turn = result.get("turns", [{}])[-1] if result.get("turns") else {}
        lines.append(
            "| {case_id} | {feature} | {summary} | `{hint}` | {actual} | {shot} |".format(
                case_id=result.get("case_id", ""),
                feature=cut(result.get("feature"), 30),
                summary=cut(result.get("summary"), 60),
                hint=result.get("visual_hint", ""),
                actual=cut(turn.get("actual_text_extract") or result.get("error"), 110),
                shot=turn.get("late_response_screenshot") or result.get("error_screenshot", ""),
            )
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="移动灵犀快速视觉补测：短等待+截图优先")
    parser.add_argument("--case-source", type=Path, default=DEFAULT_CASE_SOURCE)
    parser.add_argument("--review-source", type=Path, default=DEFAULT_REVIEW_SOURCE)
    parser.add_argument("--third-review-source", type=Path, default=DEFAULT_THIRD_REVIEW_SOURCE)
    parser.add_argument("--case-ids", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--wait-s", type=float, default=12.0)
    parser.add_argument("--extra-wait-s", type=float, default=5.0)
    parser.add_argument("--include-format", action="store_true")
    parser.add_argument("--force-stop-first", action="store_true")
    parser.add_argument("--skip-done-from", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = select_cases(load_cases(args.case_source), args)
    if not selected:
        raise SystemExit("没有选中任何补测用例")
    run_id = datetime.now().strftime("mobile-lingxi-fast-visual-%Y%m%d-%H%M%S")
    run_dir = Path("reports/mobile_lingxi_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.force_stop_first:
        force_stop_app()
    launch_app()
    device = set_fast_input()
    metadata = {
        "run_id": run_id,
        "mode": "fast_visual_recapture",
        "selected_cases": len(selected),
        "case_ids": [case["case_id"] for case in selected],
        "case_source": str(args.case_source),
        "review_source": str(args.review_source),
        "third_review_source": str(args.third_review_source),
        "wait_s": args.wait_s,
        "extra_wait_s": args.extra_wait_s,
        "start_time": now(),
        "device": str(adb(["devices", "-l"], timeout=10)).strip(),
        "foreground": foreground_summary(),
        "app": PACKAGE,
        "app_version": app_version(),
    }
    results: list[dict[str, Any]] = []
    progress = run_dir / "progress.log"
    write_reports(run_dir, metadata, results)
    for index, case in enumerate(selected, start=1):
        line = f"{now()} START {index}/{len(selected)} {case['case_id']} {case.get('feature','')}"
        print(line, flush=True)
        progress.open("a", encoding="utf-8").write(line + "\n")
        result = run_case(run_dir, device, case, args)
        results.append(result)
        metadata["updated_at"] = now()
        write_reports(run_dir, metadata, results)
        line = (
            f"{now()} END {index}/{len(selected)} {case['case_id']} "
            f"status={result.get('status')} hint={result.get('visual_hint')} duration_ms={result.get('duration_ms')}"
        )
        print(line, flush=True)
        progress.open("a", encoding="utf-8").write(line + "\n")
    metadata["end_time"] = now()
    metadata["updated_at"] = metadata["end_time"]
    write_reports(run_dir, metadata, results)
    print(f"RESULT_DIR {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
