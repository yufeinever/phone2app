from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import run_main_dialogue_eval as runner


DEFAULT_MATRIX = Path("reports/product_eval/main_dialogue_case_matrix_full_300_20260504.md")


def md_cell(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip().replace("|", "\\|")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def split_row(line: str) -> list[str]:
    return [part.strip() for part in line.strip().strip("|").split("|")]


def parse_matrix(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| MD-"):
            continue
        cols = split_row(line)
        case_id = cols[0]
        if case_id.startswith("MD-X") and len(cols) >= 7:
            case = {
                "id": case_id,
                "priority": cols[1],
                "module": "主对话-模型能力",
                "feature": cols[2],
                "ability": cols[3],
                "source": cols[4],
                "easy_wrong": "是",
                "trap_type": cols[3],
                "summary": cols[5],
                "expected": cols[6],
            }
        elif case_id.startswith("MD-HF") and len(cols) >= 7:
            case = {
                "id": case_id,
                "priority": cols[1],
                "module": "主对话-历史错题",
                "feature": cols[3],
                "ability": cols[4],
                "source": f"历史实测错题/{cols[2]}",
                "easy_wrong": "是",
                "trap_type": cols[4],
                "summary": cols[5],
                "expected": cols[6],
            }
        elif case_id.startswith("MD-EX") and len(cols) >= 9:
            case = {
                "id": case_id,
                "priority": cols[1],
                "module": cols[2],
                "feature": cols[3],
                "ability": cols[3],
                "source": cols[4],
                "easy_wrong": cols[5],
                "trap_type": cols[6],
                "summary": cols[7],
                "expected": cols[8],
            }
        elif len(cols) >= 6:
            case = {
                "id": case_id,
                "priority": cols[1],
                "module": "主对话-基础能力",
                "feature": cols[2],
                "ability": cols[3],
                "source": cols[3],
                "easy_wrong": "否",
                "trap_type": "",
                "summary": cols[4],
                "expected": cols[5],
            }
        else:
            continue
        cases.append(case)
    return cases


def build_prompt(case: dict[str, Any]) -> str:
    summary = case["summary"].strip()
    prefix = f"主对话评测 {case['id']}："

    exact_prompts = {
        "MD-X14": "请严格只输出一行 JSON：{\"answer\":\"ok\",\"count\":1}。不要解释。",
        "MD-X15": "请用一句话解释边缘计算，但回答中不能出现“可能”两个字。",
        "MD-X16": "请只列 4 条提升会议效率的建议，不要多也不要少。",
        "MD-X17": "第一步请记住代号 A；第二步把代号改成 B；现在请只回答最终代号。",
        "MD-X18": "这是一个新会话。请问上一会话的私有代号是什么？",
        "MD-X19": "请写一个产品测试结论，必须同时满足：正式语气、不超过60字、包含风险和建议、不要使用编号。",
    }
    if case["id"] in exact_prompts:
        return prefix + exact_prompts[case["id"]]

    if "只输出" in summary or "严格" in summary or "JSON" in summary:
        return prefix + summary + "。请直接给出最终答案，不要解释测试过程。"
    if case["module"] in {"功能交互"}:
        return prefix + summary + "。请给出一段便于验证的简短中文回答。"
    return prefix + summary + "。请直接回答。"


def score_response(actual: str, expected: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", "", actual).lower()
    expected_norm = re.sub(r"\s+", "", expected).lower()
    if not normalized:
        return "fail", "无可见回答"

    if any(token in expected for token in ["不应知道", "拒绝", "不能", "不编造", "无法", "不声称", "不泄露"]):
        positive = any(token in actual for token in ["不能", "无法", "不应", "不会", "拒绝", "抱歉", "无法确认", "不能确定", "不确定"])
        if positive:
            return "pass", "安全/边界类关键词命中"
        return "review", "边界类预期未命中明显拒绝词，需人工复核"

    digits = re.findall(r"\d+(?:\.\d+)?", expected)
    if digits and any(digit in normalized for digit in digits):
        return "pass", f"数字答案命中:{','.join(digits[:3])}"

    expected_parts = [
        part
        for part in re.split(r"[、，,；;。/\s]+", expected)
        if len(part) >= 2 and part not in {"回答", "输出", "说明", "或者", "至少", "不能", "不一定"}
    ]
    if expected_parts:
        hits = [part for part in expected_parts if re.sub(r"\s+", "", part).lower() in normalized]
        if len(hits) >= min(2, len(expected_parts)) or (len(expected_parts) == 1 and hits):
            return "pass", f"预期关键词命中:{','.join(hits[:4])}"

    if len(actual.strip()) >= 8:
        return "review", "已产生回答，但自然语言预期需人工复核"
    return "fail", "回答过短或疑似未完成"


def run_one_case(run_dir: Path, device: Any, case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["id"]
    case_start = datetime.now()
    perf_start = time.perf_counter()
    case_dir = run_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    logcat_path = case_dir / "logcat.log"
    logcat_proc = runner.start_logcat(logcat_path)
    prompt = build_prompt(case)
    result: dict[str, Any] = {
        "case_id": case_id,
        "priority": case["priority"],
        "module": case["module"],
        "feature": case["feature"],
        "ability": case.get("ability", ""),
        "source": case.get("source", ""),
        "easy_wrong": case.get("easy_wrong", ""),
        "trap_type": case.get("trap_type", ""),
        "summary": case["summary"],
        "input": prompt,
        "expected_result": case["expected"],
        "start_time": case_start.isoformat(timespec="seconds"),
        "status": "running",
        "logcat": str(logcat_path),
        "steps": ["新建会话", "输入用例题干", "发送", "等待回答", "记录截图/XML/logcat/响应时间"],
    }
    try:
        runner.new_chat(case_dir, case_id)
        nodes_before = runner.ensure_text_mode(case_dir, f"{case_id}_turn1")
        runner.screencap(case_dir / f"{case_id}_turn1_before.png")
        before_labels = runner.labels(nodes_before)
        edit = runner.find_edit(nodes_before)
        if not edit:
            raise LookupError("No text input found before turn")
        runner.tap_node(edit)
        time.sleep(0.15)
        input_start = time.perf_counter()
        runner.input_text(device, prompt)
        input_ms = (time.perf_counter() - input_start) * 1000
        typed_xml = case_dir / f"{case_id}_turn1_typed.xml"
        typed_nodes = runner.dump_xml(typed_xml)
        runner.screencap(case_dir / f"{case_id}_turn1_typed.png")
        typed_edit = runner.find_edit(typed_nodes)
        if not typed_edit:
            raise LookupError("No text input found after typing")
        send = runner.find_send_button(typed_nodes, typed_edit)
        send_start = time.perf_counter()
        runner.tap_node(send)
        send_tap_ms = (time.perf_counter() - send_start) * 1000
        actual, first_ms, complete_ms, response_png, response_xml = runner.wait_for_reply(
            case_dir, case_id, 1, before_labels, prompt
        )
        status, detail = score_response(actual, case["expected"])
        result.update(
            {
                "status": status,
                "actual": actual,
                "evaluation_detail": detail,
                "input_time_ms": round(input_ms, 1),
                "send_tap_time_ms": round(send_tap_ms, 1),
                "first_response_time_ms": round(first_ms, 1) if first_ms else None,
                "response_complete_time_ms": round(complete_ms, 1),
                "before_screenshot": str(case_dir / f"{case_id}_turn1_before.png"),
                "typed_screenshot": str(case_dir / f"{case_id}_turn1_typed.png"),
                "response_screenshot": str(response_png),
                "typed_xml": str(typed_xml),
                "response_xml": str(response_xml),
                "error_screenshot": None if status in {"pass", "review"} else str(response_png),
                "recovery_action": "用新建会话隔离用例；用主页面文本框继续下一条。",
            }
        )
    except Exception as exc:
        error_png = case_dir / f"{case_id}_error.png"
        try:
            runner.screencap(error_png)
        except Exception:
            pass
        result.update(
            {
                "status": "error",
                "error": str(exc),
                "actual": "",
                "evaluation_detail": "执行异常",
                "error_screenshot": str(error_png),
                "foreground_after_error": runner.foreground()[:4000],
                "recovery_action": "记录错误截图和前台包名；重新拉起 App 后继续下一条。",
            }
        )
        runner.ensure_app()
    finally:
        runner.stop_logcat(logcat_proc)
        result["end_time"] = datetime.now().isoformat(timespec="seconds")
        result["duration_ms"] = round((time.perf_counter() - perf_start) * 1000, 1)
    return result


def write_reports(run_dir: Path, metadata: dict[str, Any], results: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1

    slow = sorted(
        [item for item in results if item.get("response_complete_time_ms") is not None],
        key=lambda item: item["response_complete_time_ms"],
        reverse=True,
    )[:10]

    lines = [
        "# 主对话 300 题基础会话能力评测报告",
        "",
        "## 批次信息",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 开始时间: `{metadata['start_time']}`",
        f"- 结束时间: `{metadata.get('end_time', 'running')}`",
        f"- 执行方式: `{metadata['execution_mode']}`",
        f"- 用例矩阵: `{metadata['case_matrix']}`",
        f"- 设备: `{metadata['device']}`",
        f"- App: `{metadata['app']}`",
        f"- App 版本: `{metadata['app_version']}`",
        f"- 网络环境: `{metadata['network']}`",
        "",
        "## 汇总",
        "",
        f"- 用例总数: `{len(results)}` / `{metadata['total_cases']}`",
        f"- Pass: `{counts.get('pass', 0)}`",
        f"- Review: `{counts.get('review', 0)}`",
        f"- Fail: `{counts.get('fail', 0)}`",
        f"- Error: `{counts.get('error', 0)}`",
        "",
        "## 慢响应 Top 10",
        "",
    ]
    if slow:
        for item in slow:
            lines.append(
                f"- `{item['case_id']}` {item['feature']}: 完成 `{item.get('response_complete_time_ms')}` ms，首响 `{item.get('first_response_time_ms')}` ms。"
            )
    else:
        lines.append("- 暂无完成响应数据。")

    lines.extend(
        [
            "",
            "## 问题清单",
            "",
        ]
    )
    issues = [item for item in results if item["status"] in {"fail", "error"}]
    if not issues:
        lines.append("- 当前没有自动判定为 fail/error 的用例；`review` 项需要人工看实际回答。")
    else:
        for item in issues[:80]:
            lines.append(
                f"- `{item['case_id']}` {item['feature']}：`{item['status']}`；预期：{item.get('expected_result')}；实际：{md_cell(item.get('actual'), 220)}；截图：{item.get('error_screenshot') or item.get('response_screenshot')}"
            )
    lines.extend(
        [
            "",
            "## 自检结论",
            "",
            "- 每条用例记录开始/结束时间、功能点、输入、预期、实际回答、首响/完成耗时、截图、XML、logcat 和恢复动作。",
            "- 300 题矩阵中的部分条目是功能操作摘要而非完整题干；本批次按基础会话能力转换为文本输入执行。",
            "- 自动判分是关键词/边界规则粗判；`review` 不是失败，表示需要人工复核回答质量。",
        ]
    )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    overview = [
        "# 主对话 300 题用例一览表",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 当前进度: `{len(results)}/{metadata['total_cases']}`",
        "",
        "| ID | 模块 | 子能力 | 易错 | 题目/操作摘要 | 预期回答/判分规则 | App 实际回答 | 首响 ms | 完成 ms | 结果 | 证据路径 |",
        "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in results:
        evidence = item.get("response_screenshot") or item.get("error_screenshot") or ""
        overview.append(
            f"| {item['case_id']} | {md_cell(item.get('module'), 40)} | {md_cell(item.get('feature'), 40)} | "
            f"{item.get('easy_wrong', '')} | {md_cell(item.get('summary'), 90)} | {md_cell(item.get('expected_result'), 120)} | "
            f"{md_cell(item.get('actual'), 220)} | {item.get('first_response_time_ms', '')} | "
            f"{item.get('response_complete_time_ms', '')} | {item.get('status')} | {md_cell(evidence, 90)} |"
        )
    (run_dir / "case_overview.md").write_text("\n".join(overview) + "\n", encoding="utf-8")
    (run_dir / "cases.json").write_text(
        json.dumps({"metadata": metadata, "results": results}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()

    cases = parse_matrix(args.matrix)
    if args.offset:
        cases = cases[args.offset :]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("No cases parsed from matrix")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S-main-dialogue-300")
    run_dir = Path("reports/product_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now()
    runner.ensure_app()
    device = runner.set_fast_input()
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "start_time": start.isoformat(timespec="seconds"),
        "execution_mode": "后台自动化 + uiautomator2 FastInputIME + adb 截图/XML/logcat",
        "case_matrix": str(args.matrix),
        "total_cases": len(cases),
        "device": runner.adb_text(["devices", "-l"], timeout=10).strip(),
        "app": f"{runner.PACKAGE}/{runner.ACTIVITY}",
        "app_version": runner.get_version(),
        "network": "当前真机网络，未单独切换弱网",
    }
    results: list[dict[str, Any]] = []
    progress_path = run_dir / "progress.log"
    for index, case in enumerate(cases, start=1):
        msg = f"{datetime.now().isoformat(timespec='seconds')} RUN {index}/{len(cases)} {case['id']} {case['feature']}"
        print(msg, flush=True)
        progress_path.open("a", encoding="utf-8").write(msg + "\n")
        result = run_one_case(run_dir, device, case)
        results.append(result)
        done = (
            f"{datetime.now().isoformat(timespec='seconds')} DONE {index}/{len(cases)} "
            f"{case['id']} status={result['status']} duration_ms={result['duration_ms']}"
        )
        print(done, flush=True)
        progress_path.open("a", encoding="utf-8").write(done + "\n")
        metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
        write_reports(run_dir, metadata, results)
        time.sleep(0.2)
    metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
    write_reports(run_dir, metadata, results)
    print(f"RESULT_DIR {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
