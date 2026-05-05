from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from .adb import Adb, AdbError
from .config import load_config
from .reporting import compare_reports, generate_markdown, write_json
from .runner import run_suite


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="phone2app", description="Android real-device app performance toolkit.")
    parser.add_argument("--adb", help="Path to adb executable.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="Check local adb/device/config readiness.")
    _add_common_config_args(doctor_parser)
    doctor_parser.add_argument("--serial", help="adb device serial.")

    run_parser = subparsers.add_parser("run", help="Run configured scenarios and collect metrics.")
    _add_common_config_args(run_parser)
    run_parser.add_argument("--serial", help="adb device serial.")
    run_parser.add_argument("--output", default="reports", help="Output directory.")
    run_parser.add_argument("--package", help="Override app package.")
    run_parser.add_argument("--activity", help="Override app activity.")

    compare_parser = subparsers.add_parser("compare", help="Compare a report with a baseline.")
    compare_parser.add_argument("--current", required=True, help="Current report.json.")
    compare_parser.add_argument("--baseline", required=True, help="Baseline report.json.")
    compare_parser.add_argument("--thresholds", default="configs/thresholds.yaml", help="Threshold YAML.")
    compare_parser.add_argument("--output", help="Optional JSON output path.")

    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return doctor(args)
        if args.command == "run":
            return run(args)
        if args.command == "compare":
            return compare(args)
    except (AdbError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 1


def _add_common_config_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device-config", default="configs/devices.yaml", help="Device config YAML.")
    parser.add_argument("--scenario-config", default="configs/scenarios.yaml", help="Scenario config YAML.")


def doctor(args: argparse.Namespace) -> int:
    device_config = load_config(args.device_config)
    scenario_config = load_config(args.scenario_config)
    adb = Adb(serial=args.serial, adb_path=args.adb)
    device = adb.choose_device(args.serial or _configured_serial(device_config))
    info = adb.device_info()
    app = scenario_config.get("app", {})
    print("adb:", adb.adb_path)
    print("device:", device.serial, device.model or "", info.get("android_version", ""))
    print("package:", app.get("package") or "<missing>")
    print("activity:", app.get("activity") or "<not set>")
    print("scenarios:", len([s for s in scenario_config.get("scenarios", []) if s.get("enabled", True)]))
    if not app.get("package"):
        raise ValueError("configs/scenarios.yaml app.package is required.")
    return 0


def run(args: argparse.Namespace) -> int:
    device_config = load_config(args.device_config)
    scenario_config = load_config(args.scenario_config)
    if args.package:
        scenario_config.setdefault("app", {})["package"] = args.package
    if args.activity:
        scenario_config.setdefault("app", {})["activity"] = args.activity
    adb = Adb(serial=args.serial, adb_path=args.adb)
    report = run_suite(
        adb=adb,
        scenario_config=scenario_config,
        configured_serial=args.serial or _configured_serial(device_config),
        output_root=Path(args.output),
    )
    report_dir = Path(report["output_dir"])
    write_json(report_dir / "report.json", report)
    (report_dir / "report.md").write_text(generate_markdown(report), encoding="utf-8")
    latest = Path(args.output) / "latest"
    try:
        latest.mkdir(parents=True, exist_ok=True)
        write_json(latest / "report.json", report)
        (latest / "report.md").write_text(generate_markdown(report), encoding="utf-8")
    except OSError:
        pass
    print(f"report: {report_dir / 'report.md'}")
    print(f"json: {report_dir / 'report.json'}")
    return 0


def compare(args: argparse.Namespace) -> int:
    current = _read_json(args.current)
    baseline = _read_json(args.baseline)
    thresholds = load_config(args.thresholds)
    comparison = compare_reports(current, baseline, thresholds)
    text = json.dumps(comparison, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if comparison["status"] != "fail" else 1


def _configured_serial(device_config: Dict[str, Any]) -> Optional[str]:
    devices = device_config.get("devices") or []
    if not devices:
        return None
    return devices[0].get("serial")


def _read_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
