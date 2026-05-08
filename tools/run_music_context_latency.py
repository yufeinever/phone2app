from __future__ import annotations

import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_music_shortcut_latency as base


TEAM_CONTEXT = "我现在非常困，非常想睡觉，我喜欢助眠的音乐"
OTHER_CONTEXT = TEAM_CONTEXT
MUSIC_PROMPT = "来点音乐"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def context_match(text: str) -> dict[str, Any]:
    positive = ["助眠", "睡", "困", "放松", "舒缓", "安静", "轻音乐", "白噪音", "催眠", "入眠", "睡前", "温柔", "轻柔"]
    negative = ["热歌", "热门", "摇滚", "劲爆", "嗨", "动感", "燃", "快节奏"]
    hits = [word for word in positive if word in text]
    neg = [word for word in negative if word in text]
    return {
        "context_related": bool(hits) and not (len(neg) > len(hits)),
        "positive_hits": hits,
        "negative_hits": neg,
    }


def write_text(device: Any, text: str) -> None:
    try:
        device.send_keys(text, clear=True)
    except Exception:
        device.send_keys(text, clear=False)


def find_team_send(nodes: list[base.Node], edit: base.Node) -> base.Node | None:
    candidates = [
        node
        for node in nodes
        if node.clickable
        and node.cls == "android.widget.ImageView"
        and node.bounds[0] >= edit.bounds[2] - 20
        and node.bounds[1] >= edit.bounds[1] - 80
        and node.bounds[3] >= edit.bounds[3] - 10
    ]
    return max(candidates, key=lambda item: item.bounds[2]) if candidates else None


def find_mobile_send(nodes: list[base.Node]) -> base.Node | None:
    for suffix in (":id/ll_txt_send", ":id/iv_send", ":id/btn_send"):
        node = base.find_by_id(nodes, suffix)
        if node:
            return node
    candidates = [node for node in nodes if node.clickable and node.bounds[2] > 900 and node.bounds[1] > 1850]
    return max(candidates, key=lambda item: (item.bounds[2], item.bounds[3])) if candidates else None


def find_doubao_send(nodes: list[base.Node]) -> base.Node | None:
    return base.find_by_id(nodes, ":id/action_send")


def recover_doubao_text(nodes: list[base.Node], case_dir: Path, prefix: str) -> list[base.Node]:
    if base.find_by_id(nodes, ":id/input_text"):
        return nodes
    action = base.find_by_id(nodes, ":id/action_input")
    if action:
        base.tap_node(action)
        time.sleep(0.5)
        return base.dump_xml(case_dir / f"{prefix}_after_text_mode.xml")
    return nodes


def _xml_bounds_top(raw: str) -> int:
    nums = [int(item) for item in re.findall(r"\d+", raw)]
    return nums[1] if len(nums) >= 4 else 0


def recover_mobile_duplicate_shortcut_reply(
    case_dir: Path, result: dict[str, object], poll_log: list[dict[str, object]]
) -> dict[str, object]:
    if result.get("status") == "ok":
        return result
    first_ms: float | None = None
    complete_ms: float | None = None
    actual = ""
    response_xml: Path | None = None
    stable = 0
    for row in poll_log:
        poll = int(row.get("poll", 0))
        elapsed = float(row.get("elapsed_ms", 0))
        path = case_dir / f"poll_{poll:03d}.xml"
        if not path.exists():
            continue
        root = ET.parse(path).getroot()
        loading = bool(row.get("loading"))
        messages: list[tuple[int, str]] = []
        for node in root.iter("node"):
            text = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
            resource_id = node.attrib.get("resource-id", "")
            if "message_state" in resource_id and text:
                loading = True
            if "message_text" in resource_id and text:
                messages.append((_xml_bounds_top(node.attrib.get("bounds", "")), text))
        messages.sort()
        prompt_y = max((top for top, text in messages if text == MUSIC_PROMPT), default=None)
        if prompt_y is None:
            stable = 0
            continue
        replies = [
            text
            for top, text in messages
            if top > prompt_y and text != MUSIC_PROMPT and text not in (TEAM_CONTEXT, OTHER_CONTEXT)
        ]
        if replies:
            actual = replies[-1]
            response_xml = path
            if first_ms is None:
                first_ms = elapsed
            if not loading:
                stable += 1
            else:
                stable = 0
            if stable >= 2:
                complete_ms = elapsed
                break
        else:
            stable = 0
    if first_ms is None or not actual:
        return result
    result["actual"] = actual
    result["estimated_output_tokens"] = base.estimate_tokens(actual)
    result["first_response_time_ms"] = round(first_ms, 1)
    result["response_complete_time_ms"] = round(complete_ms if complete_ms is not None else first_ms, 1)
    if response_xml:
        result["response_xml"] = str(response_xml)
    result["status"] = "ok"
    result["context_judgement"] = context_match(actual)
    result["duplicate_reply_recovered_from_xml_order"] = True
    return result


def send_text_turn(
    product: str,
    package: str,
    case_dir: Path,
    nodes: list[base.Node],
    prompt: str,
    timeout_s: float,
    prefix: str,
) -> tuple[dict[str, object], list[base.Node]]:
    device = base.set_fast_input()
    if product == "team":
        edit = next((node for node in nodes if node.cls == "android.widget.EditText"), None)
    elif product == "mobile":
        edit = base.find_by_id(nodes, ":id/et_input")
    elif product == "doubao":
        nodes = recover_doubao_text(nodes, case_dir, prefix)
        edit = base.find_by_id(nodes, ":id/input_text")
    else:
        raise ValueError(product)
    if not edit:
        raise RuntimeError(f"{product} 未找到文本输入框")

    before = base.page_labels(nodes, package)
    base.tap_node(edit)
    time.sleep(0.2)
    write_text(device, prompt)
    typed_nodes = base.dump_xml(case_dir / f"{prefix}_typed.xml")
    base.screencap(case_dir / f"{prefix}_typed.png")
    if product == "team":
        typed_edit = next((node for node in typed_nodes if node.cls == "android.widget.EditText"), edit)
        send = find_team_send(typed_nodes, typed_edit)
    elif product == "mobile":
        send = find_mobile_send(typed_nodes)
    else:
        send = find_doubao_send(typed_nodes)
    if not send:
        raise RuntimeError(f"{product} 输入后未找到发送按钮")
    base.tap_node(send)
    started = time.perf_counter()
    wait_before = before + [prompt]
    actual, first_ms, complete_ms, png, xml, poll_log = base.wait_for_stable_answer(
        product, package, case_dir, wait_before, started, timeout_s
    )
    result = base.build_result(
        {"team": "团队版灵犀", "mobile": "移动灵犀", "doubao": "豆包"}[product],
        "input_send",
        actual,
        first_ms,
        complete_ms,
        png,
        xml,
        poll_log,
    )
    result["input"] = prompt
    next_nodes = base.dump_xml(case_dir / f"{prefix}_after_response.xml")
    return result, next_nodes


def trigger_music_shortcut(
    product: str,
    package: str,
    case_dir: Path,
    nodes: list[base.Node],
    timeout_s: float,
    swipes: int,
) -> dict[str, object]:
    before, started = base.find_and_click_music_shortcut(product, package, case_dir, nodes, swipes)
    actual, first_ms, complete_ms, png, xml, poll_log = base.wait_for_stable_answer(
        product, package, case_dir, before, started, timeout_s
    )
    result = base.build_result(
        {"mobile": "移动灵犀", "doubao": "豆包"}[product],
        "context_then_shortcut_click",
        actual,
        first_ms,
        complete_ms,
        png,
        xml,
        poll_log,
    )
    result["input"] = MUSIC_PROMPT
    result["context_judgement"] = context_match(actual)
    if product == "mobile":
        result = recover_mobile_duplicate_shortcut_reply(case_dir, result, poll_log)
    return result


def run_product(product: str, run_dir: Path, timeout_s: float, swipes: int) -> dict[str, object]:
    case_dir = run_dir / product
    case_dir.mkdir(parents=True, exist_ok=True)
    if product == "team":
        nodes = base.team_new_chat(case_dir)
        context, nodes = send_text_turn(
            "team", base.TEAM_PACKAGE, case_dir, nodes, TEAM_CONTEXT, timeout_s, "context_turn"
        )
        music, _nodes = send_text_turn(
            "team", base.TEAM_PACKAGE, case_dir, nodes, MUSIC_PROMPT, timeout_s, "music_turn"
        )
        music["trigger"] = "context_then_input_send"
        music["context_judgement"] = context_match(str(music.get("actual", "")))
    elif product == "mobile":
        nodes = base.mobile_open_new_chat(case_dir)
        context, nodes = send_text_turn(
            "mobile", base.MOBILE_PACKAGE, case_dir, nodes, OTHER_CONTEXT, timeout_s, "context_turn"
        )
        music = trigger_music_shortcut("mobile", base.MOBILE_PACKAGE, case_dir, nodes, timeout_s, swipes)
    elif product == "doubao":
        nodes = base.doubao_open_new_chat(case_dir)
        context, nodes = send_text_turn(
            "doubao", base.DOUBAO_PACKAGE, case_dir, nodes, OTHER_CONTEXT, timeout_s, "context_turn"
        )
        music = trigger_music_shortcut("doubao", base.DOUBAO_PACKAGE, case_dir, nodes, timeout_s, swipes)
    else:
        raise ValueError(product)
    return {
        "product": {"team": "团队版灵犀", "mobile": "移动灵犀", "doubao": "豆包"}[product],
        "context_turn": context,
        "music_turn": music,
        "status": "ok" if music.get("status") == "ok" else music.get("status", "unknown"),
    }


def write_report(run_dir: Path, metadata: dict[str, object], results: list[dict[str, object]]) -> None:
    (run_dir / "results.json").write_text(
        json.dumps({"metadata": metadata, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 来点音乐上下文关联测试",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 设备: `{metadata['device_serial']}`",
        f"- 开始时间: `{metadata['start_time']}`",
        f"- 结束时间: `{metadata.get('end_time', '')}`",
        "",
        "| App | 前置上下文 | 触发方式 | first-token ms | 完全回答 ms | token估算 | 上下文关联 | 命中词 | 回答摘要 | 截图 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
    ]
    for item in results:
        context_turn = item.get("context_turn", {})
        music = item.get("music_turn", {})
        judgement = music.get("context_judgement", {}) if isinstance(music, dict) else {}
        actual = str(music.get("actual", "") if isinstance(music, dict) else "").replace("\n", " ")
        if len(actual) > 130:
            actual = actual[:129] + "..."
        actual = actual.replace("|", "\\|")
        hits = ",".join(judgement.get("positive_hits", [])) if isinstance(judgement, dict) else ""
        context_input = str(context_turn.get("input", "")).replace("|", "\\|")
        lines.append(
            f"| {item.get('product')} | {context_input} | "
            f"{music.get('trigger', '') if isinstance(music, dict) else ''} | "
            f"{music.get('first_response_time_ms', '') if isinstance(music, dict) else ''} | "
            f"{music.get('response_complete_time_ms', '') if isinstance(music, dict) else ''} | "
            f"{music.get('estimated_output_tokens', '') if isinstance(music, dict) else ''} | "
            f"{judgement.get('context_related', '') if isinstance(judgement, dict) else ''} | {hits} | "
            f"{actual} | {music.get('response_screenshot', '') if isinstance(music, dict) else ''} |"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="先上下文后点击/输入来点音乐的关联测试")
    parser.add_argument("--products", default="team,mobile,doubao")
    parser.add_argument("--timeout-s", type=float, default=60)
    parser.add_argument("--shortcut-swipes", type=int, default=10)
    parser.add_argument("--output-root", type=Path, default=Path("reports/music_context_latency"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = [part.strip() for part in args.products.split(",") if part.strip()]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-music-context")
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, object] = {
        "run_id": run_id,
        "start_time": now(),
        "device_serial": base.SERIAL,
        "products": selected,
        "team_context": TEAM_CONTEXT,
        "mobile_doubao_context": OTHER_CONTEXT,
        "music_prompt": MUSIC_PROMPT,
    }
    results: list[dict[str, object]] = []
    for product in selected:
        print(f"{now()} RUN {product}", flush=True)
        try:
            result = run_product(product, run_dir, args.timeout_s, args.shortcut_swipes)
        except Exception as exc:
            result = {
                "product": product,
                "status": "error",
                "error": str(exc),
            }
        results.append(result)
        music = result.get("music_turn", {}) if isinstance(result, dict) else {}
        print(
            f"{now()} DONE {product} status={result.get('status')} "
            f"first_ms={music.get('first_response_time_ms') if isinstance(music, dict) else ''} "
            f"complete_ms={music.get('response_complete_time_ms') if isinstance(music, dict) else ''} "
            f"context={music.get('context_judgement', {}).get('context_related') if isinstance(music, dict) else ''}",
            flush=True,
        )
        write_report(run_dir, metadata, results)
    metadata["end_time"] = now()
    write_report(run_dir, metadata, results)
    print(f"RESULT_DIR {run_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
