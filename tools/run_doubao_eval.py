from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from doubao_common import (
    MAIN_ACTIVITY,
    PACKAGE,
    SERIAL,
    Node,
    adb,
    adb_no_raise,
    capture_state,
    dump_xml,
    find_input,
    find_send,
    force_stop_app,
    foreground_summary,
    has_app_nodes,
    has_answer_actions,
    is_loading,
    launch_app,
    node_json,
    open_new_chat,
    page_text,
    recover_to_text_chat,
    screencap,
    tap_node,
    u2_device,
)


DEFAULT_SOURCE = Path("reports/product_eval/main-dialogue-300-v2.1-20260505/cases.json")

SMOKE_IDS = [
    "MD-X13",      # 苹果/香蕉/梨拼音排序，历史易错
    "MD-X17",      # 多轮新旧信息覆盖
    "MD-X19",      # 5 轮约束保持
    "MD-F03",      # 长材料摘要
    "MD-F05",      # 短期上下文记忆
    "MD-F07",      # 新会话隔离
    "MD-I01",      # 严格格式/JSON
    "MD-EX-C08",   # 话题切换后回到上下文
    "MD-EX-C11",   # 长上下文检索
    "MD-EX-S18",   # 多轮安全拒答边界
]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    results = raw.get("results") if isinstance(raw, dict) else raw
    cases: list[dict[str, Any]] = []
    for item in results:
        if "turns" in item:
            turns = [
                {
                    "input": turn.get("input", ""),
                    "expected": turn.get("expected") or turn.get("expected_result", ""),
                    "old_app_actual": turn.get("actual", ""),
                    "action": "new_chat" if turn.get("input") == "__NEW_CHAT__" else turn.get("action", ""),
                    "scoring_type": turn.get("scoring_type") or item.get("scoring_type", ""),
                    "strict_answer_only": bool(turn.get("strict_answer_only") or item.get("scoring_type") == "single_choice_abcd"),
                }
                for turn in item["turns"]
            ]
        else:
            turns = [
                {
                    "input": item.get("input", ""),
                    "expected": item.get("expected_result", ""),
                    "old_app_actual": item.get("actual", ""),
                    "action": "",
                    "scoring_type": item.get("scoring_type", ""),
                    "strict_answer_only": item.get("scoring_type") == "single_choice_abcd",
                }
            ]
        cases.append(
            {
                "case_id": item.get("case_id") or item.get("id"),
                "priority": item.get("priority", ""),
                "module": item.get("module", ""),
                "feature": item.get("feature", ""),
                "ability": item.get("ability", ""),
                "source": item.get("source", ""),
                "easy_wrong": item.get("easy_wrong", ""),
                "trap_type": item.get("trap_type", ""),
                "summary": item.get("summary", ""),
                "steps": item.get("steps", ["新建会话", "输入题干", "发送", "等待回答", "记录截图/XML/时延"]),
                "expected_result": item.get("expected_result", ""),
                "turns": turns,
            }
        )
    return [case for case in cases if case["case_id"] and any(t["input"] for t in case["turns"])]


def select_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.case_ids:
        wanted = [part.strip() for part in args.case_ids.split(",") if part.strip()]
        by_id = {case["case_id"]: case for case in cases}
        return [by_id[cid] for cid in wanted if cid in by_id]
    if args.mode == "smoke":
        by_id = {case["case_id"]: case for case in cases}
        picked = [by_id[cid] for cid in SMOKE_IDS if cid in by_id]
        if len(picked) < 10:
            seen = {case["case_id"] for case in picked}
            for case in cases:
                if case["case_id"] not in seen:
                    picked.append(case)
                    seen.add(case["case_id"])
                if len(picked) >= 10:
                    break
        return picked[: args.limit] if args.limit else picked[:10]
    limit = args.limit or len(cases)
    return cases[:limit]


def csv_set(value: str) -> set[str]:
    return {part.strip() for part in (value or "").split(",") if part.strip()}


def load_run_results(path: Path) -> list[dict[str, Any]]:
    cases_path = path / "cases.json" if path.is_dir() else path
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    return raw.get("results", []) if isinstance(raw, dict) else raw


def app_version() -> str:
    out = str(adb(["shell", "dumpsys", "package", PACKAGE], timeout=20))
    version_name = "unknown"
    version_code = "unknown"
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            version_name = line.split("=", 1)[1]
        if line.startswith("versionCode="):
            version_code = line.split("=", 1)[1].split()[0]
    return f"{version_name} ({version_code})"


def parse_meminfo(text: str) -> dict[str, int]:
    metrics: dict[str, int] = {}
    key_map = {
        "TOTAL PSS": "total_pss_kb",
        "TOTAL": "total_kb",
        "Java Heap": "java_heap_kb",
        "Native Heap": "native_heap_kb",
        "Graphics": "graphics_kb",
        "Views": "views",
        "Activities": "activities",
        "WebViews": "webviews",
    }
    for line in text.splitlines():
        for match in re.finditer(r"([A-Za-z ]+?):\s+([\d,]+)", line):
            key = key_map.get(match.group(1).strip())
            if key:
                metrics[key] = int(match.group(2).replace(",", ""))
    return metrics


def collect_observation(run_dir: Path, sequence: int, case_id: str, phase: str) -> dict[str, Any]:
    observation_dir = run_dir / "observations"
    observation_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{sequence:04d}_{case_id}_{phase}"
    meminfo_path = observation_dir / f"{prefix}_meminfo.txt"
    focus_path = observation_dir / f"{prefix}_foreground.txt"
    meminfo = adb_no_raise(["shell", "dumpsys", "meminfo", PACKAGE], timeout=25)
    foreground = foreground_summary()
    meminfo_path.write_text(meminfo, encoding="utf-8")
    focus_path.write_text(foreground, encoding="utf-8")
    observation = {
        "time": now(),
        "sequence": sequence,
        "case_id": case_id,
        "phase": phase,
        "foreground": foreground,
        "metrics": parse_meminfo(meminfo),
        "meminfo_path": str(meminfo_path),
        "foreground_path": str(focus_path),
    }
    with (run_dir / "observations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(observation, ensure_ascii=False) + "\n")
    return observation


def set_fast_input() -> Any:
    device = u2_device()
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


def snapshot_turn(case_dir: Path, prefix: str) -> tuple[Path, Path, list[Node], str]:
    png = case_dir / f"{prefix}.png"
    xml = case_dir / f"{prefix}.xml"
    nodes = dump_xml(xml)
    screencap(png)
    return png, xml, nodes, page_text(nodes)


def normalize_visible_text(text: str) -> list[str]:
    noise = {
        "新对话",
        "内容由豆包 AI 生成",
        "快速",
        "拍题答疑",
        "AI 创作",
        "豆包 P 图",
        "录音纪要",
        "发消息或按住说话...",
        "深度思考，已关闭",
        "语音输入",
        "更多面板",
        "相机",
        "复制",
        "朗读",
        "收藏",
        "分享",
        "重新生成",
        "回到底部",
        "设置页",
        "返回",
        "开启性能模式",
        "开启 NFC",
        "蓝牙开启。",
        "振铃器静音。",
        "WLAN 信号强度满格。",
        "无 SIM 卡。",
        "正在充电，已完成百分之100。",
        "100",
    }
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line in noise:
            continue
        if len(line) == 5 and line[2] == ":" and line[:2].isdigit() and line[3:].isdigit():
            continue
        lines.append(line)
    return lines


def answer_from_nodes(nodes: list[Node], before_text: str, prompt: str) -> str:
    before_set = set(normalize_visible_text(before_text))
    prompt = prompt.strip()
    prompt_norm = re.sub(r"\s+", "", prompt)
    prompt_bottom = 0
    for node in nodes:
        if node.package == PACKAGE and node.text.strip() == prompt:
            prompt_bottom = max(prompt_bottom, node.bounds[3])
    candidates = []
    for node in nodes:
        text = node.text.strip()
        if node.package != PACKAGE or node.cls != "android.widget.TextView" or not text:
            continue
        left, top, _right, _bottom = node.bounds
        if text == prompt:
            continue
        text_norm = re.sub(r"\s+", "", text)
        if prompt_norm and (
            text_norm in prompt_norm
            or prompt_norm in text_norm
            or (len(text_norm) >= 80 and text_norm in prompt_norm)
        ):
            continue
        if text in {"新对话", "内容由豆包 AI 生成", "快速", "拍题答疑", "AI 创作", "豆包 P 图", "回到底部"}:
            continue
        if prompt_bottom and top + 10 < prompt_bottom:
            continue
        if left > 650:
            continue
        candidates.append((top, text))
    if candidates:
        return "\n".join(text for _top, text in sorted(candidates)[-8:])
    after_lines = normalize_visible_text(page_text(nodes))
    diff = [line for line in after_lines if line not in before_set and line != prompt]
    if "请仅回答选项" in prompt:
        for line in diff:
            if re.fullmatch(r"[A-Da-d]", line.strip()):
                return line.strip().upper()
        return ""
    return "\n".join(diff[-8:])


def find_back_to_bottom(nodes: list[Node]) -> Node | None:
    for node in nodes:
        if node.resource_id.endswith(":id/fast_button_icon") and node.desc == "回到底部":
            return node
    return None


def wait_for_response(case_dir: Path, prefix: str, before_text: str, prompt: str, timeout_s: float) -> tuple[str, float, float, Path, Path]:
    start = time.perf_counter()
    first_ms: float | None = None
    stable_count = 0
    last_answer = ""
    best_answer = ""
    last_png = case_dir / f"{prefix}_response.png"
    last_xml = case_dir / f"{prefix}_response.xml"
    while (time.perf_counter() - start) < timeout_s:
        png, xml, nodes, _visible = snapshot_turn(case_dir, f"{prefix}_poll")
        last_png, last_xml = png, xml
        if not has_app_nodes(nodes):
            time.sleep(0.5)
            continue
        loading = is_loading(nodes)
        answer = answer_from_nodes(nodes, before_text, prompt)
        back_to_bottom = find_back_to_bottom(nodes)
        if back_to_bottom and not answer:
            tap_node(back_to_bottom)
            time.sleep(0.8)
            continue
        if not answer and (time.perf_counter() - start) > 2.0:
            adb(["shell", "input", "swipe", "540", "1780", "540", "820", "260"], timeout=10)
            time.sleep(0.8)
            continue
        if answer and first_ms is None:
            first_ms = (time.perf_counter() - start) * 1000
        if answer:
            best_answer = answer
        if not loading and answer and answer == last_answer:
            stable_count += 1
        else:
            stable_count = 0
            last_answer = answer
        if not loading and answer and (stable_count >= 2 or has_answer_actions(nodes)):
            break
        time.sleep(0.5)
    complete_ms = (time.perf_counter() - start) * 1000
    return best_answer or last_answer, first_ms or 0.0, complete_ms, last_png, last_xml


def simple_score(expected: str, actual: str) -> tuple[str, str]:
    expected = (expected or "").strip()
    actual = (actual or "").strip()
    if not actual:
        return "fail", "未抓取到回答"
    if not expected:
        return "review", "无自动判分预期"
    compact_actual = actual.replace(" ", "").replace("\n", "")
    if "status=ok" in expected and "count=3" in expected:
        if "status" in compact_actual and "ok" in compact_actual and "count" in compact_actual and "3" in compact_actual:
            return "pass", "JSON 关键字段命中"
    if expected.startswith("确认"):
        if any(word in actual for word in ["已记住", "已记录", "已添加", "已更新", "已阅读"]):
            return "pass", "确认类回答命中"
    if "；" in expected or ";" in expected:
        parts = [part.strip() for part in expected.replace(";", "；").split("；") if part.strip()]
        if parts and all(part in actual for part in parts):
            return "pass", "多关键词全部命中"
    if len(expected) >= 2 and expected in actual:
        return "pass", "预期文本直接命中"
    return "review", "自然语言预期，需人工/GPT复核"


UI_CHROME_TEXT = {
    "回到底部",
    "复制",
    "朗读",
    "重新生成",
    "分享",
    "发送",
    "输入消息",
    "有什么问题尽管问我",
}


def strict_abcd_score(expected: str, actual: str) -> tuple[str, str]:
    expected = (expected or "").strip().upper()
    raw = actual or ""
    compact_actual = re.sub(r"\s+", "", raw).upper()
    if not compact_actual:
        return "fail", "未抓取到回答"
    if expected in {"A", "B", "C", "D"} and compact_actual == expected:
        return "pass", f"严格单选命中 expected={expected}"
    lines = [line.strip() for line in raw.replace("\r", "\n").split("\n") if line.strip()]
    signal_lines = [line for line in lines if line not in UI_CHROME_TEXT]
    if len(signal_lines) == 1 and expected in {"A", "B", "C", "D"} and signal_lines[0].upper() == expected:
        return "pass", f"严格单选命中 expected={expected} ignored_ui={len(lines)-1}"
    return "fail", f"严格单选失败 expected={expected} actual={compact_actual!r}"


def score_turn(turn: dict[str, Any], actual: str) -> tuple[str, str]:
    if turn.get("scoring_type") == "single_choice_abcd" or turn.get("strict_answer_only"):
        return strict_abcd_score(turn.get("expected", ""), actual)
    return simple_score(turn.get("expected", ""), actual)


def run_case(run_dir: Path, device: Any, case: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    case_id = case["case_id"]
    case_dir = run_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "case_id": case_id,
        "module": case.get("module", ""),
        "feature": case.get("feature", ""),
        "ability": case.get("ability", ""),
        "priority": case.get("priority", ""),
        "source": case.get("source", ""),
        "easy_wrong": case.get("easy_wrong", ""),
        "trap_type": case.get("trap_type", ""),
        "summary": case.get("summary", ""),
        "expected_result": case.get("expected_result", ""),
        "start_time": now(),
        "steps": case.get("steps", []),
        "turns": [],
        "recovery_action": "每个用例前通过豆包侧栏创建新对话；失败时保留截图/XML/logcat，后续人工恢复或重跑。",
    }
    try:
        open_new_chat(case_dir, f"{case_id}_new_chat")
        previous_visible = ""
        turn_statuses = []
        for idx, turn in enumerate(case["turns"], start=1):
            prefix = f"{case_id}_turn{idx}"
            if turn.get("action") == "new_chat":
                started = now()
                open_new_chat(case_dir, f"{prefix}_action_new_chat")
                result["turns"].append(
                    {
                        "turn_index": idx,
                        "input": "__NEW_CHAT__",
                        "expected": turn.get("expected", "新建会话"),
                        "old_app_actual": turn.get("old_app_actual", ""),
                        "actual": "已执行新建会话动作",
                        "status": "pass",
                        "evaluation_detail": "automation_action:new_chat",
                        "start_time": started,
                        "end_time": now(),
                        "input_time_ms": 0.0,
                        "send_tap_time_ms": 0.0,
                        "first_response_time_ms": 0.0,
                        "response_complete_time_ms": 0.0,
                        "before_screenshot": "",
                        "typed_screenshot": "",
                        "response_screenshot": "",
                        "before_xml": "",
                        "typed_xml": "",
                        "response_xml": "",
                        "error_screenshot": None,
                    }
                )
                turn_statuses.append("pass")
                previous_visible = ""
                continue
            nodes = recover_to_text_chat(case_dir, f"{prefix}_recover")
            edit = find_input(nodes)
            if not edit:
                raise RuntimeError("未找到豆包输入框 input_text")
            before_png, before_xml, _nodes, before_text = snapshot_turn(case_dir, f"{prefix}_before")
            tap_node(edit)
            input_ms = type_text(device, turn["input"])
            typed_png, typed_xml, typed_nodes, _typed_text = snapshot_turn(case_dir, f"{prefix}_typed")
            send = find_send(typed_nodes)
            if not send:
                raise RuntimeError("输入后未找到豆包发送按钮 action_send")
            send_start = time.perf_counter()
            tap_node(send)
            send_ms = (time.perf_counter() - send_start) * 1000
            actual, first_ms, complete_ms, response_png, response_xml = wait_for_response(
                case_dir, prefix, previous_visible or before_text, turn["input"], timeout_s
            )
            status, detail = score_turn(turn, actual)
            turn_statuses.append(status)
            previous_nodes = dump_xml(case_dir / f"{prefix}_after_response.xml")
            previous_visible = page_text(previous_nodes)
            result["turns"].append(
                {
                    "turn_index": idx,
                    "input": turn["input"],
                    "expected": turn.get("expected", ""),
                    "old_app_actual": turn.get("old_app_actual", ""),
                    "actual": actual,
                    "status": status,
                    "evaluation_detail": detail,
                    "start_time": result["start_time"],
                    "end_time": now(),
                    "input_time_ms": round(input_ms, 1),
                    "send_tap_time_ms": round(send_ms, 1),
                    "first_response_time_ms": round(first_ms, 1),
                    "response_complete_time_ms": round(complete_ms, 1),
                    "before_screenshot": str(before_png),
                    "typed_screenshot": str(typed_png),
                    "response_screenshot": str(response_png),
                    "before_xml": str(before_xml),
                    "typed_xml": str(typed_xml),
                    "response_xml": str(response_xml),
                    "error_screenshot": None,
                }
            )
        if any(status == "fail" for status in turn_statuses):
            result["status"] = "fail"
        elif any(status == "review" for status in turn_statuses):
            result["status"] = "review"
        else:
            result["status"] = "pass"
    except Exception as exc:
        err_png = case_dir / f"{case_id}_error.png"
        err_xml = case_dir / f"{case_id}_error.xml"
        err_logcat = case_dir / f"{case_id}_error_logcat.txt"
        try:
            screencap(err_png)
            nodes = dump_xml(err_xml)
            (case_dir / f"{case_id}_error.nodes.json").write_text(
                json.dumps(node_json(nodes), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        err_logcat.write_text(adb_no_raise(["logcat", "-d", "-t", "300"], timeout=20), encoding="utf-8")
        result["status"] = "error"
        result["error"] = str(exc)
        result["error_screenshot"] = str(err_png)
        result["error_xml"] = str(err_xml)
        result["error_logcat"] = str(err_logcat)
    result["end_time"] = now()
    result["duration_ms"] = round(
        (datetime.fromisoformat(result["end_time"]) - datetime.fromisoformat(result["start_time"])).total_seconds() * 1000,
        1,
    )
    return result


def write_reports(run_dir: Path, metadata: dict[str, Any], results: list[dict[str, Any]]) -> None:
    payload = {"metadata": metadata, "results": results}
    (run_dir / "cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total = len(results)
    pass_count = sum(1 for r in results if r.get("status") == "pass")
    review_count = sum(1 for r in results if r.get("status") == "review")
    fail_count = sum(1 for r in results if r.get("status") in {"fail", "error"})
    lines = [
        "# 豆包主对话评测",
        "",
        f"- Run ID：`{metadata['run_id']}`",
        f"- App：`{metadata['app']}`",
        f"- App 版本：`{metadata['app_version']}`",
        f"- 开始时间：{metadata['start_time']}",
        f"- 结束时间：{metadata.get('end_time', '')}",
        f"- 统计：总数 {total}，通过 {pass_count}，待复核 {review_count}，失败/错误 {fail_count}",
        "",
        "## 用例一览表",
        "",
        "| 用例ID | 模块 | 能力 | 题目摘要 | 预期回答/规则 | 豆包回答 | 首字时延ms | 完成时延ms | 结果 | 截图 |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]

    def cut(value: Any, size: int = 80) -> str:
        text = str(value or "").replace("\n", "<br>").replace("|", "\\|")
        return text[:size] + ("..." if len(text) > size else "")

    for result in results:
        turn = result.get("turns", [{}])[-1] if result.get("turns") else {}
        lines.append(
            "| {case_id} | {module} | {ability} | {summary} | {expected} | {actual} | {first} | {complete} | {status} | {shot} |".format(
                case_id=result.get("case_id", ""),
                module=result.get("module", ""),
                ability=result.get("ability") or result.get("feature", ""),
                summary=cut(result.get("summary") or turn.get("input"), 60),
                expected=cut(turn.get("expected") or result.get("expected_result"), 70),
                actual=cut(turn.get("actual") or result.get("error"), 90),
                first=turn.get("first_response_time_ms", ""),
                complete=turn.get("response_complete_time_ms", ""),
                status=result.get("status", ""),
                shot=turn.get("response_screenshot") or result.get("error_screenshot", ""),
            )
        )
    (run_dir / "case_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_dir / "summary.md").write_text("\n".join(lines[:10]) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="豆包主对话专用评测执行器")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--case-source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--case-ids", default="", help="逗号分隔的用例 ID；指定后覆盖 mode 选择")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout-s", type=float, default=25.0)
    parser.add_argument("--max-consecutive-errors", type=int, default=3)
    parser.add_argument("--restart-every", type=int, default=0, help="调试用；稳定性测试保持 0")
    parser.add_argument("--no-observation", action="store_true", help="关闭每题前后 meminfo/foreground 观测")
    parser.add_argument("--force-stop-first", action="store_true", help="执行前先 force-stop 豆包")
    parser.add_argument("--resume-from-run", type=Path, action="append", default=[], help="从已有报告目录或 cases.json 断点续跑；后传入结果覆盖先传入结果")
    parser.add_argument("--rerun-status", default="", help="逗号分隔的状态；断点续跑时仅重跑这些状态，例如 error,fail")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected_cases = select_cases(load_cases(args.case_source), args)
    if not selected_cases:
        raise SystemExit("没有选中任何用例")
    selected_ids = [case["case_id"] for case in selected_cases]
    selected_id_set = set(selected_ids)

    result_by_id: dict[str, dict[str, Any]] = {}
    rerun_statuses = csv_set(args.rerun_status)
    for resume_path in args.resume_from_run:
        for result in load_run_results(resume_path):
            case_id = result.get("case_id")
            if case_id in selected_id_set:
                result_by_id[case_id] = result

    cases_to_run: list[tuple[int, dict[str, Any]]] = []
    for index, case in enumerate(selected_cases, start=1):
        previous = result_by_id.get(case["case_id"])
        if not previous or previous.get("status") in rerun_statuses:
            cases_to_run.append((index, case))

    def ordered_results() -> list[dict[str, Any]]:
        return [result_by_id[case_id] for case_id in selected_ids if case_id in result_by_id]

    run_id = datetime.now().strftime(f"%Y%m%d-%H%M%S-doubao-{args.mode}")
    run_dir = Path("reports/doubao_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.force_stop_first:
        force_stop_app()
    launch_app()
    capture_state(run_dir, "00_before_eval")
    device = set_fast_input()
    metadata = {
        "run_id": run_id,
        "mode": args.mode,
        "case_source": str(args.case_source),
        "selected_cases": len(selected_cases),
        "resume_from_run": [str(path) for path in args.resume_from_run],
        "previous_results_loaded": len(result_by_id),
        "rerun_status": args.rerun_status,
        "cases_to_run": len(cases_to_run),
        "restart_every": args.restart_every,
        "observation_enabled": not args.no_observation,
        "observation_policy": "每题前后采集 dumpsys meminfo 与 foreground；默认不重启 App，以暴露稳定性问题。",
        "start_time": now(),
        "device": str(adb(["devices", "-l"], timeout=10)).strip(),
        "foreground": foreground_summary(),
        "app": f"{PACKAGE}/{MAIN_ACTIVITY}",
        "app_version": app_version(),
        "network": "当前真机网络，未切换弱网",
        "smoke_selector_note": "豆包专用 selector：input_text/action_send/back_icon/side_bar_create_conversation。",
    }
    progress = run_dir / "progress.log"
    if args.resume_from_run:
        resume_line = (
            f"{now()} RESUME source={metadata['resume_from_run']} loaded={metadata['previous_results_loaded']} "
            f"selected={len(selected_cases)} to_run={len(cases_to_run)} rerun_status={args.rerun_status or '-'}"
        )
        print(resume_line, flush=True)
        progress.open("a", encoding="utf-8").write(resume_line + "\n")
        write_reports(run_dir, metadata, ordered_results())
    consecutive_errors = 0
    for index, case in cases_to_run:
        if args.restart_every and index > 1 and (index - 1) % args.restart_every == 0:
            force_stop_app()
            launch_app()
            device = set_fast_input()
        line = f"{now()} START {index}/{len(selected_cases)} {case['case_id']} {case.get('summary', '')}"
        print(line, flush=True)
        progress.open("a", encoding="utf-8").write(line + "\n")
        if not args.no_observation:
            collect_observation(run_dir, index, case["case_id"], "before")
        result = run_case(run_dir, device, case, args.timeout_s)
        result_by_id[case["case_id"]] = result
        if not args.no_observation:
            collect_observation(run_dir, index, case["case_id"], "after")
        if result["status"] == "error":
            consecutive_errors += 1
        else:
            consecutive_errors = 0
        done = (
            f"{now()} DONE {index}/{len(selected_cases)} {case['case_id']} "
            f"status={result['status']} duration_ms={result.get('duration_ms')}"
        )
        print(done, flush=True)
        progress.open("a", encoding="utf-8").write(done + "\n")
        metadata["end_time"] = now()
        write_reports(run_dir, metadata, ordered_results())
        if consecutive_errors >= args.max_consecutive_errors:
            stop = f"{now()} STOP consecutive_errors={consecutive_errors}"
            print(stop, flush=True)
            progress.open("a", encoding="utf-8").write(stop + "\n")
            break
    metadata["end_time"] = now()
    capture_state(run_dir, "99_after_eval")
    write_reports(run_dir, metadata, ordered_results())
    print(str(run_dir.resolve()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
