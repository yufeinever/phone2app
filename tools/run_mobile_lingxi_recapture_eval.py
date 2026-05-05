from __future__ import annotations

import argparse
import json
import re
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
    has_app_nodes,
    launch_app,
    open_new_chat,
    page_text,
    recover_to_text_chat,
    screencap,
    tap_node,
)
from run_mobile_lingxi_eval import app_version, collect_observation, load_cases, simple_score


DEFAULT_CASE_SOURCE = Path("data/eval_cases/main-dialogue-300-v3.2/dialogue_cases.json")
DEFAULT_REVIEW_SOURCE = Path(
    "reports/compare_eval/rotating-main-dialogue-274-wrong-review-batches-20260505/"
    "wrong_answer_second_review.json"
)
DEFAULT_THIRD_REVIEW_SOURCE = Path(
    "reports/compare_eval/rotating-main-dialogue-274-wrong-review-batches-20260505/"
    "mobile_lingxi_keep_wrong_third_review_20260505.json"
)

INTERMEDIATE_PATTERNS = [
    "正在搜索",
    "搜索中",
    "资料整理",
]

ROUTE_OR_STATE_PATTERNS = [
    "想要我怎么称呼你",
    "修改昵称",
    "日程管理",
    "在此输入内容开启新话题",
    "发送内容后",
    "将开启新对话",
    "在此输入您的问题",
]

CAPTURE_FRAGMENT_PATTERNS = [
    "表格",
    "注：",
    "温馨提示",
]

NOISE_LINES = {
    "文本",
    "通话",
    "日报待阅",
    "记忆管理",
    "会议助手",
    "智能绘画",
    "在此输入您的问题~",
    "内容由 AI 生成",
    "自动播报",
    "声音配置",
    "新建对话",
    "思考",
    "Float Min",
    "关闭性格",
    "开启性能模式",
    "开启 NFC",
    "蓝牙开启。",
    "振铃器静音。",
    "WLAN 信号强度满格。",
    "无 SIM 卡。",
    "正在充电，已完成百分之100。",
    "100",
    "记忆同步状态",
    "已更新至记忆库",
    "记忆",
}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def csv_set(value: str) -> set[str]:
    return {part.strip() for part in (value or "").split(",") if part.strip()}


def set_fast_input() -> Any:
    device = u2.connect_usb(SERIAL)
    try:
        device.set_fastinput_ime(True)
    except Exception:
        if hasattr(device, "set_input_ime"):
            device.set_input_ime(True)
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


def normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in NOISE_LINES:
            continue
        if len(line) == 5 and line[2] == ":" and line[:2].isdigit() and line[3:].isdigit():
            continue
        if line.startswith("主对话评测 "):
            continue
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return lines


def is_intermediate(text: str) -> bool:
    compact = text.replace(" ", "")
    if any(pattern in compact for pattern in INTERMEDIATE_PATTERNS):
        return True
    if re.fullmatch(r"已联网搜索到\d+个网页", compact):
        return True
    if re.fullmatch(r"已搜索到\d+个资料", compact):
        return True
    return False


def is_route_or_state(text: str) -> bool:
    return any(pattern in text for pattern in ROUTE_OR_STATE_PATTERNS)


def is_suspicious_fragment(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if stripped == "表格":
        return True
    if len(stripped) <= 12 and any(pattern in stripped for pattern in CAPTURE_FRAGMENT_PATTERNS):
        return True
    if stripped.endswith(("：", ":", "；")):
        return True
    return False


def extract_answer(before_text: str, visible_text: str, prompts: list[str]) -> str:
    before_set = set(normalize_lines(before_text))
    prompt_set = {prompt.strip() for prompt in prompts if prompt.strip()}
    lines = normalize_lines(visible_text)
    candidates = [
        line
        for line in lines
        if line not in before_set and line not in prompt_set and not any(line == prompt for prompt in prompt_set)
    ]
    if candidates:
        return "\n".join(candidates[-10:])
    fallback = [line for line in lines if line not in prompt_set]
    return "\n".join(fallback[-10:])


def collect_scroll_pages(case_dir: Path, prefix: str, pages: int) -> dict[str, Any]:
    pages_payload: list[dict[str, Any]] = []
    combined_lines: list[str] = []
    seen: set[str] = set()
    for index in range(1, pages + 1):
        png, xml, nodes, visible = snapshot(case_dir, f"{prefix}_scroll{index}")
        lines = normalize_lines(visible)
        for line in lines:
            if line not in seen:
                seen.add(line)
                combined_lines.append(line)
        pages_payload.append(
            {
                "page": index,
                "screenshot": str(png),
                "xml": str(xml),
                "visible_text": visible,
                "has_app_nodes": has_app_nodes(nodes),
            }
        )
        adb_no_raise(["shell", "input", "swipe", "540", "760", "540", "1660", "450"], timeout=10)
        time.sleep(0.7)
    return {
        "pages": pages_payload,
        "combined_visible_text": "\n".join(combined_lines),
    }


def wait_for_response_recapture(
    case_dir: Path,
    prefix: str,
    before_text: str,
    prompts: list[str],
    timeout_s: float,
    min_wait_s: float,
    stable_polls: int,
    poll_interval_s: float,
) -> dict[str, Any]:
    start = time.perf_counter()
    first_ms: float | None = None
    stable_count = 0
    last_answer = ""
    best_answer = ""
    poll_log: list[dict[str, Any]] = []
    while (time.perf_counter() - start) < timeout_s:
        poll_index = len(poll_log) + 1
        png, xml, nodes, visible = snapshot(case_dir, f"{prefix}_poll{poll_index:02d}")
        has_nodes = has_app_nodes(nodes)
        answer = extract_answer(before_text, visible, prompts) if has_nodes else ""
        elapsed_ms = (time.perf_counter() - start) * 1000
        intermediate = is_intermediate(answer) or is_intermediate(visible)
        route_state = is_route_or_state(answer) or is_route_or_state(visible)
        suspicious = is_suspicious_fragment(answer)
        poll_log.append(
            {
                "poll": poll_index,
                "elapsed_ms": round(elapsed_ms, 1),
                "screenshot": str(png),
                "xml": str(xml),
                "has_app_nodes": has_nodes,
                "answer": answer,
                "intermediate": intermediate,
                "route_or_state": route_state,
                "suspicious_fragment": suspicious,
            }
        )
        if answer and first_ms is None and not intermediate:
            first_ms = elapsed_ms
        if answer and not intermediate:
            if len(answer) >= len(best_answer):
                best_answer = answer
        elif answer and not best_answer:
            best_answer = answer
        if answer == last_answer and answer and not intermediate and not suspicious:
            stable_count += 1
        else:
            stable_count = 0
            last_answer = answer
        if elapsed_ms >= min_wait_s * 1000 and stable_count >= stable_polls and not route_state:
            break
        time.sleep(poll_interval_s)
    complete_ms = (time.perf_counter() - start) * 1000
    (case_dir / f"{prefix}_poll_log.json").write_text(
        json.dumps(poll_log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    last = poll_log[-1] if poll_log else {}
    return {
        "actual": best_answer or last_answer,
        "first_response_time_ms": round(first_ms or 0.0, 1),
        "response_complete_time_ms": round(complete_ms, 1),
        "last_screenshot": last.get("screenshot", ""),
        "last_xml": last.get("xml", ""),
        "poll_log": str(case_dir / f"{prefix}_poll_log.json"),
        "poll_count": len(poll_log),
    }


def classify_recapture(actual: str, combined_text: str, status: str) -> tuple[str, str]:
    text = "\n".join(part for part in [actual, combined_text] if part).strip()
    if status == "error":
        return "automation_error", "执行脚本报错，需要先看 error 截图/XML/logcat。"
    if not text:
        return "no_answer", "补测仍未抓到可读回答。"
    if is_route_or_state(text):
        return "product_route_or_state", "回答或页面混入日程/昵称/新话题等产品状态，优先按产品状态污染处理。"
    if is_intermediate(text):
        return "still_intermediate", "补测后仍停留在搜索/资料整理中间态。"
    if is_suspicious_fragment(actual):
        return "needs_visual_review", "文本抓取仍像片段或富文本占位，需要人工看截图/滚动页。"
    if status in {"pass", "review"}:
        return "recaptured_answer", "已补采到可读回答，可送裁判或人工复核。"
    return "needs_manual_review", "有可读内容但自动状态不明确，需要人工复核。"


def load_mobile_product_issue_ids(
    review_source: Path,
    third_review_source: Path,
    include_format: bool,
) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    second_raw = json.loads(review_source.read_text(encoding="utf-8"))
    second_rows = second_raw.get("results", second_raw if isinstance(second_raw, list) else [])
    for row in second_rows:
        if row.get("product") != "移动灵犀":
            continue
        decision = row.get("second_review_decision")
        include = decision == "exclude_capture_or_product_failure"
        include = include or (include_format and decision == "format_or_capture_needs_screenshot")
        if include and row.get("case_id") not in seen:
            seen.add(row["case_id"])
            ids.append(row["case_id"])

    if third_review_source.exists():
        third_raw = json.loads(third_review_source.read_text(encoding="utf-8"))
        third_rows = third_raw.get("results", third_raw if isinstance(third_raw, list) else [])
        for row in third_rows:
            decision = row.get("third_review_decision")
            include = decision == "exclude_capture_or_product_failure"
            include = include or (include_format and decision == "format_or_capture_needs_screenshot")
            if include and row.get("case_id") not in seen:
                seen.add(row["case_id"])
                ids.append(row["case_id"])
    return ids


def select_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.case_ids:
        wanted = [part.strip() for part in args.case_ids.split(",") if part.strip()]
    else:
        wanted = load_mobile_product_issue_ids(args.review_source, args.third_review_source, args.include_format)
    if args.exclude_case_ids:
        excluded = csv_set(args.exclude_case_ids)
        wanted = [case_id for case_id in wanted if case_id not in excluded]
    if args.limit:
        wanted = wanted[: args.limit]
    by_id = {case["case_id"]: case for case in cases}
    missing = [case_id for case_id in wanted if case_id not in by_id]
    if missing:
        print(f"WARN missing case ids: {','.join(missing)}", flush=True)
    return [by_id[case_id] for case_id in wanted if case_id in by_id]


def run_case(run_dir: Path, device: Any, case: dict[str, Any], args: argparse.Namespace, sequence: int) -> dict[str, Any]:
    case_id = case["case_id"]
    case_dir = run_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "case_id": case_id,
        "module": case.get("module", ""),
        "feature": case.get("feature", ""),
        "ability": case.get("ability", ""),
        "summary": case.get("summary", ""),
        "expected_result": case.get("expected_result", ""),
        "start_time": now(),
        "turns": [],
        "recapture_policy": {
            "timeout_s": args.timeout_s,
            "min_wait_s": args.min_wait_s,
            "stable_polls": args.stable_polls,
            "scroll_pages": args.scroll_pages,
        },
    }
    try:
        if not args.no_observation:
            result["observation_before"] = collect_observation(run_dir, sequence, case_id, "before")
        open_new_chat(case_dir, f"{case_id}_new_chat")
        previous_visible = ""
        prompts_so_far: list[str] = []
        statuses: list[str] = []
        final_scroll: dict[str, Any] = {}
        for idx, turn in enumerate(case["turns"], start=1):
            prefix = f"{case_id}_turn{idx}"
            nodes = recover_to_text_chat(case_dir, f"{prefix}_recover")
            edit = find_input(nodes)
            if not edit:
                raise RuntimeError("未找到移动灵犀输入框 id/et_input")
            before_png, before_xml, _before_nodes, before_text = snapshot(case_dir, f"{prefix}_before")
            tap_node(edit)
            input_ms = type_text(device, turn["input"])
            typed_png, typed_xml, typed_nodes, _typed_text = snapshot(case_dir, f"{prefix}_typed")
            send = find_send(typed_nodes)
            if not send:
                raise RuntimeError("输入后未找到发送按钮 id/ll_txt_send")
            send_start = time.perf_counter()
            tap_node(send)
            send_ms = (time.perf_counter() - send_start) * 1000
            prompts_so_far.append(turn["input"])
            wait_result = wait_for_response_recapture(
                case_dir=case_dir,
                prefix=prefix,
                before_text=previous_visible or before_text,
                prompts=prompts_so_far,
                timeout_s=args.timeout_s,
                min_wait_s=args.min_wait_s,
                stable_polls=args.stable_polls,
                poll_interval_s=args.poll_interval_s,
            )
            final_scroll = collect_scroll_pages(case_dir, prefix, args.scroll_pages) if args.scroll_pages else {}
            combined = final_scroll.get("combined_visible_text", "")
            # Do not let scroll pages replace the primary answer. On this app,
            # scroll capture can include old chat-history text from adjacent
            # sessions. The combined text is evidence for visual review only.
            actual = wait_result["actual"]
            status, detail = simple_score(turn.get("expected", ""), actual)
            statuses.append(status)
            previous_visible = combined or page_text(dump_xml(case_dir / f"{prefix}_after_response.xml"))
            result["turns"].append(
                {
                    "turn_index": idx,
                    "input": turn["input"],
                    "expected": turn.get("expected", ""),
                    "actual": actual,
                    "status": status,
                    "evaluation_detail": detail,
                    "start_time": result["start_time"],
                    "end_time": now(),
                    "input_time_ms": round(input_ms, 1),
                    "send_tap_time_ms": round(send_ms, 1),
                    "first_response_time_ms": wait_result["first_response_time_ms"],
                    "response_complete_time_ms": wait_result["response_complete_time_ms"],
                    "poll_count": wait_result["poll_count"],
                    "poll_log": wait_result["poll_log"],
                    "before_screenshot": str(before_png),
                    "typed_screenshot": str(typed_png),
                    "response_screenshot": wait_result["last_screenshot"],
                    "before_xml": str(before_xml),
                    "typed_xml": str(typed_xml),
                    "response_xml": wait_result["last_xml"],
                    "scroll_capture": final_scroll,
                }
            )
        if any(status == "fail" for status in statuses):
            result["status"] = "fail"
        elif any(status == "review" for status in statuses):
            result["status"] = "review"
        else:
            result["status"] = "pass"
        final_actual = result["turns"][-1]["actual"] if result["turns"] else ""
        combined_text = final_scroll.get("combined_visible_text", "") if final_scroll else ""
        label, note = classify_recapture(final_actual, combined_text, result["status"])
        result["recapture_classification"] = label
        result["recapture_note"] = note
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
        result["error"] = str(exc)
        result["error_screenshot"] = str(err_png)
        result["error_xml"] = str(err_xml)
        result["error_logcat"] = str(err_logcat)
        label, note = classify_recapture("", "", "error")
        result["recapture_classification"] = label
        result["recapture_note"] = note
    if not args.no_observation:
        result["observation_after"] = collect_observation(run_dir, sequence, case_id, "after")
    result["end_time"] = now()
    result["duration_ms"] = round(
        (datetime.fromisoformat(result["end_time"]) - datetime.fromisoformat(result["start_time"])).total_seconds()
        * 1000,
        1,
    )
    return result


def write_reports(run_dir: Path, metadata: dict[str, Any], results: list[dict[str, Any]]) -> None:
    payload = {"metadata": metadata, "results": results}
    (run_dir / "cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = Counter(result.get("recapture_classification", "unknown") for result in results)
    lines = [
        "# 移动灵犀产品/抓取/中间态补测报告",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 开始时间：{metadata['start_time']}",
        f"- 更新时间：{metadata.get('updated_at', '')}",
        f"- App：`{metadata['app']}`",
        f"- App 版本：`{metadata['app_version']}`",
        f"- 题数：{len(results)} / {metadata['selected_cases']}",
        f"- 补测策略：timeout={metadata['timeout_s']}s, min_wait={metadata['min_wait_s']}s, scroll_pages={metadata['scroll_pages']}",
        "",
        "## 分类统计",
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
            "| 用例 | 能力 | 题目摘要 | 补测分类 | 回答摘录 | 响应完成ms | 截图 |",
            "|---|---|---|---|---|---:|---|",
        ]
    )

    def cut(value: Any, size: int = 100) -> str:
        text = str(value or "").replace("|", "\\|").replace("\n", "<br>")
        return text[:size] + ("..." if len(text) > size else "")

    for result in results:
        turn = result.get("turns", [{}])[-1] if result.get("turns") else {}
        lines.append(
            "| {case_id} | {feature} | {summary} | `{classification}` | {actual} | {complete} | {shot} |".format(
                case_id=result.get("case_id", ""),
                feature=cut(result.get("feature"), 30),
                summary=cut(result.get("summary") or turn.get("input"), 60),
                classification=result.get("recapture_classification", ""),
                actual=cut(turn.get("actual") or result.get("error"), 120),
                complete=turn.get("response_complete_time_ms", ""),
                shot=turn.get("response_screenshot") or result.get("error_screenshot", ""),
            )
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="移动灵犀产品/抓取/中间态问题补测")
    parser.add_argument("--case-source", type=Path, default=DEFAULT_CASE_SOURCE)
    parser.add_argument("--review-source", type=Path, default=DEFAULT_REVIEW_SOURCE)
    parser.add_argument("--third-review-source", type=Path, default=DEFAULT_THIRD_REVIEW_SOURCE)
    parser.add_argument("--case-ids", default="", help="逗号分隔；指定后覆盖自动筛选")
    parser.add_argument("--exclude-case-ids", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout-s", type=float, default=75.0)
    parser.add_argument("--min-wait-s", type=float, default=12.0)
    parser.add_argument("--stable-polls", type=int, default=3)
    parser.add_argument("--poll-interval-s", type=float, default=1.0)
    parser.add_argument("--scroll-pages", type=int, default=4)
    parser.add_argument("--include-format", action="store_true", help="同时补测 format_or_capture_needs_screenshot")
    parser.add_argument("--force-stop-first", action="store_true")
    parser.add_argument("--no-observation", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = select_cases(load_cases(args.case_source), args)
    if not cases:
        raise SystemExit("没有选中任何补测用例")
    run_id = datetime.now().strftime("mobile-lingxi-recapture-%Y%m%d-%H%M%S")
    run_dir = Path("reports/mobile_lingxi_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.force_stop_first:
        force_stop_app()
    launch_app()
    device = set_fast_input()
    metadata = {
        "run_id": run_id,
        "selected_cases": len(cases),
        "case_ids": [case["case_id"] for case in cases],
        "case_source": str(args.case_source),
        "review_source": str(args.review_source),
        "third_review_source": str(args.third_review_source),
        "timeout_s": args.timeout_s,
        "min_wait_s": args.min_wait_s,
        "stable_polls": args.stable_polls,
        "poll_interval_s": args.poll_interval_s,
        "scroll_pages": args.scroll_pages,
        "include_format": args.include_format,
        "start_time": now(),
        "device": str(adb(["devices", "-l"], timeout=10)).strip(),
        "foreground": foreground_summary(),
        "app": PACKAGE,
        "app_version": app_version(),
    }
    progress = run_dir / "progress.log"
    results: list[dict[str, Any]] = []
    write_reports(run_dir, metadata, results)
    for index, case in enumerate(cases, start=1):
        line = f"{now()} START {index}/{len(cases)} {case['case_id']} {case.get('feature','')}"
        print(line, flush=True)
        progress.open("a", encoding="utf-8").write(line + "\n")
        result = run_case(run_dir, device, case, args, index)
        results.append(result)
        metadata["updated_at"] = now()
        write_reports(run_dir, metadata, results)
        line = (
            f"{now()} END {index}/{len(cases)} {case['case_id']} "
            f"status={result.get('status')} class={result.get('recapture_classification')} "
            f"duration_ms={result.get('duration_ms')}"
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
