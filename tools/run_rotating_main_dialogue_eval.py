from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


SERIAL = os.environ.get("ANDROID_SERIAL", "")
DEFAULT_CASE_SOURCE = Path("data/eval_cases/main-dialogue-300-v3.2/dialogue_cases.json")
DEFAULT_OUT_ROOT = Path("reports/compare_eval")

APPS: dict[str, dict[str, Any]] = {
    "team_lingxi": {
        "product": "团队版灵犀",
        "package": "com.chinamobile.eureka",
        "script": Path("tools/run_main_dialogue_eval.py"),
        "args": [],
        "report_root": Path("reports/product_eval"),
        "report_marker": "RESULT_DIR",
    },
    "mobile_lingxi": {
        "product": "移动灵犀",
        "package": "com.jiutian.yidonglingxi",
        "script": Path("tools/run_mobile_lingxi_eval.py"),
        "args": ["--mode", "full", "--timeout-s", "25", "--max-consecutive-errors", "5"],
        "report_root": Path("reports/mobile_lingxi_eval"),
        "report_marker": "RESULT_DIR",
    },
    "doubao": {
        "product": "豆包",
        "package": "com.larus.nova",
        "script": Path("tools/run_doubao_eval.py"),
        "args": ["--mode", "full", "--timeout-s", "25", "--max-consecutive-errors", "5", "--force-stop-first"],
        "report_root": Path("reports/doubao_eval"),
        "report_marker": "",
    },
}


def adb_cmd(args: list[str]) -> list[str]:
    return ["adb", *(['-s', SERIAL] if SERIAL else []), *args]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_case_ids(path: Path, limit: int = 0) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("results") if isinstance(raw, dict) else raw
    ids = [
        str(row.get("case_id") or row.get("id") or "").strip()
        for row in rows
        if str(row.get("case_id") or row.get("id") or "").strip()
    ]
    return ids[:limit] if limit else ids


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def run_adb(args: list[str], timeout: int = 20) -> str:
    result = subprocess.run(
        adb_cmd(args),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return (result.stdout + result.stderr).strip()


def force_stop(package: str) -> str:
    return run_adb(["shell", "am", "force-stop", package], timeout=20)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8", errors="replace").write(line + "\n")


def parse_result_dir(output_lines: list[str], report_root: Path, marker: str, started_at: float) -> str:
    for line in reversed(output_lines):
        text = line.strip()
        if marker and marker in text:
            return text.split(marker, 1)[1].strip()
        if str(report_root).replace("/", "\\") in text or str(report_root).replace("\\", "/") in text:
            candidate = Path(text)
            if candidate.exists():
                return str(candidate)
    candidates = [path for path in report_root.iterdir() if path.is_dir() and path.stat().st_mtime >= started_at - 2]
    if candidates:
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
    return ""


def merge_aggregate(aggregate_path: Path, batch_result_dir: str, product: str) -> int:
    if not batch_result_dir:
        return 0
    cases_path = Path(batch_result_dir) / "cases.json"
    if not cases_path.exists():
        return 0
    raw = json.loads(cases_path.read_text(encoding="utf-8"))
    batch_results = raw.get("results", []) if isinstance(raw, dict) else raw
    aggregate = load_json(aggregate_path, {"metadata": {"product": product, "updated_at": now()}, "results": []})
    by_id = {row.get("case_id"): row for row in aggregate.get("results", []) if row.get("case_id")}
    for row in batch_results:
        if row.get("case_id"):
            row["source_batch_result_dir"] = batch_result_dir
            by_id[row["case_id"]] = row
    aggregate["metadata"]["product"] = product
    aggregate["metadata"]["updated_at"] = now()
    aggregate["metadata"]["result_count"] = len(by_id)
    aggregate["results"] = list(by_id.values())
    write_json(aggregate_path, aggregate)
    return len(batch_results)


def write_summary(run_dir: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# 主对话轮转执行报告",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- 开始时间: `{manifest['start_time']}`",
        f"- 更新时间: `{manifest.get('updated_at', '')}`",
        f"- 题库: `{manifest['case_source']}`",
        f"- 批大小: `{manifest['batch_size']}`",
        f"- 产品顺序: `{', '.join(item['product'] for item in manifest['apps'])}`",
        "",
        "| 批次 | 题目范围 | 产品 | 状态 | 退出码 | 报告目录 |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for item in manifest.get("batches", []):
        case_range = f"{item['case_ids'][0]}..{item['case_ids'][-1]}" if item.get("case_ids") else ""
        lines.append(
            f"| {item['batch_index']} | {case_range} | {item['product']} | {item['status']} | "
            f"{item.get('returncode', '')} | {item.get('result_dir', '')} |"
        )
    lines.extend(["", "## 聚合结果", ""])
    for app in manifest["apps"]:
        aggregate = run_dir / "aggregates" / app["key"] / "cases.json"
        count = 0
        if aggregate.exists():
            count = len(load_json(aggregate, {}).get("results", []))
        lines.append(f"- `{app['product']}`: `{count}` 题，`{aggregate}`")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_batch(
    run_dir: Path,
    app_key: str,
    batch_index: int,
    batch_case_ids: list[str],
    case_source: Path,
    batch_timeout_s: int,
) -> dict[str, Any]:
    app = APPS[app_key]
    batch_log = run_dir / "logs" / f"{batch_index:03d}_{app_key}.log"
    command = [
        sys.executable,
        str(app["script"]),
        "--case-source",
        str(case_source),
        "--case-ids",
        ",".join(batch_case_ids),
        *app["args"],
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    start_perf = time.time()
    append_line(batch_log, f"{now()} COMMAND {' '.join(command)}")
    output_lines: list[str] = []
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    timed_out = False
    assert process.stdout is not None
    while True:
        line = process.stdout.readline()
        if line:
            clean = line.rstrip("\n")
            output_lines.append(clean)
            append_line(batch_log, clean)
        if process.poll() is not None:
            break
        if time.time() - start_perf > batch_timeout_s:
            timed_out = True
            process.kill()
            append_line(batch_log, f"{now()} TIMEOUT batch_timeout_s={batch_timeout_s}")
            break
    for line in process.stdout.readlines():
        clean = line.rstrip("\n")
        output_lines.append(clean)
        append_line(batch_log, clean)
    returncode = process.wait(timeout=10)
    result_dir = parse_result_dir(output_lines, app["report_root"], app["report_marker"], start_perf)
    duration_s = round(time.time() - start_perf, 1)
    aggregate_path = run_dir / "aggregates" / app_key / "cases.json"
    merged_count = merge_aggregate(aggregate_path, result_dir, app["product"])
    return {
        "batch_index": batch_index,
        "app_key": app_key,
        "product": app["product"],
        "package": app["package"],
        "case_ids": batch_case_ids,
        "start_time": datetime.fromtimestamp(start_perf).isoformat(timespec="seconds"),
        "end_time": now(),
        "duration_s": duration_s,
        "status": "timeout" if timed_out else ("completed" if returncode == 0 else "failed"),
        "returncode": returncode,
        "result_dir": result_dir,
        "merged_count": merged_count,
        "log": str(batch_log),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="三款 App 主对话评测轮转调度器")
    parser.add_argument("--case-source", type=Path, default=DEFAULT_CASE_SOURCE)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0, help="调试时限制总题数；正式保持 0")
    parser.add_argument("--apps", default="team_lingxi,mobile_lingxi,doubao")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--batch-timeout-s", type=int, default=3600)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app_keys = [part.strip() for part in args.apps.split(",") if part.strip()]
    unknown = [key for key in app_keys if key not in APPS]
    if unknown:
        raise SystemExit(f"未知 App key: {', '.join(unknown)}")
    case_ids = load_case_ids(args.case_source, args.limit)
    if not case_ids:
        raise SystemExit("没有可执行用例")
    case_batches = chunks(case_ids, args.batch_size)
    run_id = datetime.now().strftime("rotating-main-dialogue-%Y%m%d-%H%M%S")
    run_dir = args.out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    progress = run_dir / "progress.log"
    manifest_path = run_dir / "manifest.json"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "start_time": now(),
        "updated_at": now(),
        "case_source": str(args.case_source),
        "case_count": len(case_ids),
        "batch_size": args.batch_size,
        "batch_count": len(case_batches),
        "apps": [{"key": key, "product": APPS[key]["product"], "package": APPS[key]["package"]} for key in app_keys],
        "policy": "每个产品每批最多执行 batch_size 题；批次结束 force-stop 当前 App，再启动下一产品批次。",
        "batches": [],
    }
    write_json(manifest_path, manifest)
    write_summary(run_dir, manifest)
    append_line(progress, f"{now()} START run_dir={run_dir} cases={len(case_ids)} batch_size={args.batch_size} apps={app_keys}")

    previous_package = ""
    for batch_index, batch_case_ids in enumerate(case_batches, start=1):
        for app_key in app_keys:
            app = APPS[app_key]
            if previous_package:
                append_line(progress, f"{now()} FORCE_STOP previous_package={previous_package}")
                force_stop(previous_package)
            append_line(
                progress,
                f"{now()} BATCH_START batch={batch_index}/{len(case_batches)} product={app['product']} "
                f"cases={batch_case_ids[0]}..{batch_case_ids[-1]} count={len(batch_case_ids)}",
            )
            result = run_batch(run_dir, app_key, batch_index, batch_case_ids, args.case_source, args.batch_timeout_s)
            manifest["batches"].append(result)
            manifest["updated_at"] = now()
            write_json(manifest_path, manifest)
            write_summary(run_dir, manifest)
            append_line(
                progress,
                f"{now()} BATCH_DONE batch={batch_index} product={app['product']} status={result['status']} "
                f"returncode={result['returncode']} merged={result['merged_count']} result_dir={result['result_dir']}",
            )
            append_line(progress, f"{now()} FORCE_STOP current_package={app['package']}")
            force_stop(app["package"])
            previous_package = app["package"]
    manifest["end_time"] = now()
    manifest["updated_at"] = now()
    write_json(manifest_path, manifest)
    write_summary(run_dir, manifest)
    append_line(progress, f"{now()} END run_dir={run_dir}")
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
