from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adb import Adb, parse_gfxinfo, parse_meminfo_pss_kb
from .appium_runner import AppiumScenarioRunner, needs_appium
from .logs import scan_stability_events
from .perfetto import PerfettoCollector
from .reporting import summarize
from .uiauto import UiAutomator, selector_from_step


def run_suite(
    adb: Adb,
    scenario_config: Dict[str, Any],
    configured_serial: Optional[str],
    output_root: Path,
) -> Dict[str, Any]:
    app = scenario_config.get("app") or {}
    package = app.get("package")
    activity = app.get("activity")
    if not package:
        raise ValueError("app.package is required in scenario config.")

    device = adb.choose_device(configured_serial)
    info = adb.device_info()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    apk_path = app.get("apk_path")
    if apk_path:
        adb.install_apk(apk_path)

    scenarios = [scenario for scenario in scenario_config.get("scenarios", []) if scenario.get("enabled", True)]
    run_defaults = scenario_config.get("run") or {}
    perfetto = PerfettoCollector(adb)
    report_scenarios: List[Dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()

    for scenario in scenarios:
        report_scenarios.append(
            _run_scenario(
                adb=adb,
                perfetto=perfetto,
                output_dir=output_dir,
                app=app,
                scenario=scenario,
                run_defaults=run_defaults,
                package=package,
                activity=activity,
            )
        )

    report = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": _overall_status(report_scenarios),
        "output_dir": str(output_dir),
        "app": {"package": package, "activity": activity, "apk_path": apk_path},
        "device": {"serial": device.serial, **info},
        "scenarios": report_scenarios,
    }
    report["summary"] = summarize_report(report)
    return report


def _run_scenario(
    adb: Adb,
    perfetto: PerfettoCollector,
    output_dir: Path,
    app: Dict[str, Any],
    scenario: Dict[str, Any],
    run_defaults: Dict[str, Any],
    package: str,
    activity: Optional[str],
) -> Dict[str, Any]:
    name = str(scenario.get("name") or "unnamed")
    repeats = int(scenario.get("repeats", run_defaults.get("repeats", 1)))
    warmups = int(scenario.get("warmups", run_defaults.get("warmups", 0)))
    collect_perfetto = bool(scenario.get("collect_perfetto", run_defaults.get("collect_perfetto", False)))
    perfetto_seconds = int(scenario.get("perfetto_seconds", run_defaults.get("perfetto_seconds", 15)))
    cold_start = bool(scenario.get("cold_start_each_iteration", run_defaults.get("cold_start_each_iteration", True)))
    steps = scenario.get("steps") or [{"action": "launch"}]
    uid = adb.package_uid(package)

    iterations: List[Dict[str, Any]] = []
    total_iterations = warmups + repeats
    for index in range(total_iterations):
        is_warmup = index < warmups
        log_path = output_dir / "logcat" / f"{name}-{index + 1}.log"
        trace_path = output_dir / "traces" / f"{name}-{index + 1}.perfetto-trace"
        adb.clear_logcat()
        log_process = adb.logcat_process(log_path)
        trace = perfetto.start(trace_path, perfetto_seconds) if collect_perfetto else None
        started = time.perf_counter()
        startup_metrics: Dict[str, int] = {}
        step_outcomes: List[Dict[str, Any]] = []
        status = "pass"
        error = None
        net_before = adb.uid_net_bytes(uid)
        mem_before = parse_meminfo_pss_kb(adb.dump_meminfo(package))
        try:
            if cold_start:
                adb.force_stop(package)
                time.sleep(0.5)
            if needs_appium(steps):
                startup_metrics = _run_launch_steps(adb, app, package, activity, steps)
                with AppiumScenarioRunner(
                    server_url=app.get("appium_server", "http://127.0.0.1:4723"),
                    capabilities=app.get("appium_caps") or {},
                    package=package,
                    activity=activity,
                    serial=adb.serial,
                ) as appium:
                    step_outcomes = [outcome.__dict__ for outcome in appium.run_steps(steps)]
                    if any(not outcome["ok"] for outcome in step_outcomes):
                        status = "fail"
            else:
                startup_metrics, step_outcomes = _run_adb_steps(
                    adb=adb,
                    app=app,
                    package=package,
                    activity=activity,
                    steps=steps,
                    output_dir=output_dir / "ui" / f"{name}-{index + 1}",
                )
                if any(not outcome["ok"] for outcome in step_outcomes):
                    status = "fail"
        except Exception as exc:
            status = "fail"
            error = str(exc)
        finally:
            wall_time_ms = (time.perf_counter() - started) * 1000
            trace_file = perfetto.finish(trace) if trace else None
            _terminate_process(log_process)

        net_after = adb.uid_net_bytes(uid)
        mem_after = parse_meminfo_pss_kb(adb.dump_meminfo(package))
        gfxinfo = parse_gfxinfo(adb.dump_gfxinfo(package))
        stability = [event.__dict__ for event in scan_stability_events(log_path)]
        if stability:
            status = "fail"
        iteration = {
            "index": index + 1,
            "warmup": is_warmup,
            "status": status,
            "error": error,
            "wall_time_ms": wall_time_ms,
            "startup": startup_metrics,
            "steps": step_outcomes,
            "memory": {"before_pss_kb": mem_before, "after_pss_kb": mem_after, "delta_pss_kb": _delta(mem_before, mem_after)},
            "network": _net_delta(net_before, net_after),
            "gfxinfo": gfxinfo,
            "stability_events": stability,
            "logcat": str(log_path),
            "trace": trace_file,
        }
        iterations.append(iteration)

    return {
        "name": name,
        "description": scenario.get("description", ""),
        "iterations": iterations,
    }


def _run_launch_steps(adb: Adb, app: Dict[str, Any], package: str, activity: Optional[str], steps: List[Dict[str, Any]]) -> Dict[str, int]:
    startup_metrics: Dict[str, int] = {}
    for step in steps:
        action = step.get("action")
        if action == "launch":
            _, startup_metrics = adb.start_activity(package, activity)
            time.sleep(float(step.get("post_wait_seconds", app.get("post_launch_wait_seconds", 0))))
            break
    return startup_metrics


def _run_adb_steps(
    adb: Adb,
    app: Dict[str, Any],
    package: str,
    activity: Optional[str],
    steps: List[Dict[str, Any]],
    output_dir: Path,
) -> tuple:
    startup_metrics: Dict[str, int] = {}
    outcomes: List[Dict[str, Any]] = []
    ui = UiAutomator(adb, output_dir)
    for index, step in enumerate(steps, start=1):
        action = str(step.get("action"))
        started = time.perf_counter()
        ok = True
        detail = ""
        try:
            if action == "launch":
                _, startup_metrics = adb.start_activity(package, activity)
                time.sleep(float(step.get("post_wait_seconds", app.get("post_launch_wait_seconds", 0))))
                detail = str(startup_metrics)
            elif action == "wait":
                time.sleep(float(step.get("seconds", 1)))
            elif action in (
                "tap_text",
                "tap_text_contains",
                "tap_content_desc",
                "tap_content_desc_contains",
                "tap_accessibility_id",
                "tap_resource_id",
            ):
                node = ui.tap(selector_from_step(step), timeout_seconds=float(step.get("timeout_seconds", 8)))
                detail = f"{node.text or node.content_desc or node.resource_id} {node.bounds}"
            elif action in ("assert_text", "assert_text_contains", "assert_content_desc", "assert_content_desc_contains"):
                node = ui.find(selector_from_step(step), timeout_seconds=float(step.get("timeout_seconds", 8)))
                detail = f"{node.text or node.content_desc} {node.bounds}"
            elif action == "input_text":
                ui.input_text(str(step.get("value", "")))
            elif action == "press_back":
                adb.shell("input keyevent BACK", timeout=10)
            elif action == "tap_xy":
                x = int(step["x"])
                y = int(step["y"])
                adb.shell(f"input tap {x} {y}", timeout=10)
                detail = f"{x},{y}"
            else:
                raise ValueError(f"Unsupported adb automation action: {action}")
        except Exception as exc:
            ok = False
            detail = str(exc)
        outcomes.append(
            {
                "index": index,
                "action": action,
                "elapsed_ms": (time.perf_counter() - started) * 1000,
                "ok": ok,
                "detail": detail,
            }
        )
        if not ok:
            break
    return startup_metrics, outcomes


def summarize_report(report: Dict[str, Any]) -> Dict[str, Any]:
    scenarios_summary: List[Dict[str, Any]] = []
    for scenario in report.get("scenarios", []):
        measured = [iteration for iteration in scenario.get("iterations", []) if not iteration.get("warmup")]
        stability_count = {"crash": 0, "anr": 0}
        for iteration in measured:
            for event in iteration.get("stability_events", []):
                kind = event.get("kind")
                if kind in stability_count:
                    stability_count[kind] += 1
        scenarios_summary.append(
            {
                "name": scenario.get("name"),
                "wall_time_ms": summarize(iteration.get("wall_time_ms") for iteration in measured),
                "startup_total_time_ms": summarize(
                    iteration.get("startup", {}).get("TotalTime") for iteration in measured
                ),
                "startup_wait_time_ms": summarize(
                    iteration.get("startup", {}).get("WaitTime") for iteration in measured
                ),
                "memory_delta_pss_kb": summarize(
                    iteration.get("memory", {}).get("delta_pss_kb") for iteration in measured
                ),
                "network_rx_delta_bytes": summarize(
                    iteration.get("network", {}).get("rx_delta_bytes") for iteration in measured
                ),
                "network_tx_delta_bytes": summarize(
                    iteration.get("network", {}).get("tx_delta_bytes") for iteration in measured
                ),
                "stability": stability_count,
            }
        )
    return {"scenarios": scenarios_summary}


def _overall_status(scenarios: List[Dict[str, Any]]) -> str:
    for scenario in scenarios:
        for iteration in scenario.get("iterations", []):
            if iteration.get("status") == "fail":
                return "fail"
    return "pass"


def _delta(before: Optional[int], after: Optional[int]) -> Optional[int]:
    if before is None or after is None:
        return None
    return after - before


def _net_delta(before: Optional[Dict[str, int]], after: Optional[Dict[str, int]]) -> Dict[str, Optional[int]]:
    if not before or not after:
        return {"rx_delta_bytes": None, "tx_delta_bytes": None}
    return {
        "rx_delta_bytes": after.get("rx_bytes", 0) - before.get("rx_bytes", 0),
        "tx_delta_bytes": after.get("tx_bytes", 0) - before.get("tx_bytes", 0),
    }


def _terminate_process(managed_process) -> None:
    process = managed_process.process if hasattr(managed_process, "process") else managed_process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
    handle = getattr(managed_process, "handle", None)
    if handle:
        handle.close()
