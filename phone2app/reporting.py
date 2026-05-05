from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def percentile(values: Iterable[float], percent: float) -> Optional[float]:
    sorted_values = sorted(float(value) for value in values)
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * (percent / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def summarize(values: Iterable[float]) -> Dict[str, Optional[float]]:
    collected = [float(value) for value in values if value is not None]
    if not collected:
        return {"count": 0, "min": None, "max": None, "mean": None, "p50": None, "p90": None, "p95": None}
    return {
        "count": len(collected),
        "min": min(collected),
        "max": max(collected),
        "mean": statistics.mean(collected),
        "p50": percentile(collected, 50),
        "p90": percentile(collected, 90),
        "p95": percentile(collected, 95),
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# phone2app Report - {report.get('run_id')}")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append(f"- Package: `{report.get('app', {}).get('package')}`")
    lines.append(f"- Activity: `{report.get('app', {}).get('activity')}`")
    lines.append(f"- Device: `{report.get('device', {}).get('serial')}`")
    lines.append(f"- Started: `{report.get('started_at')}`")
    lines.append(f"- Status: `{report.get('status')}`")
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.append("| Scenario | Runs | Wall P90 ms | Startup P90 ms | Crash | ANR |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for scenario in report.get("summary", {}).get("scenarios", []):
        startup = scenario.get("startup_total_time_ms", {})
        wall = scenario.get("wall_time_ms", {})
        stability = scenario.get("stability", {})
        lines.append(
            f"| {scenario.get('name')} | {wall.get('count', 0)} | {_fmt(wall.get('p90'))} | "
            f"{_fmt(startup.get('p90'))} | {stability.get('crash', 0)} | {stability.get('anr', 0)} |"
        )
    lines.append("")
    lines.append("## Details")
    lines.append("")
    for scenario in report.get("scenarios", []):
        lines.append(f"### {scenario.get('name')}")
        lines.append("")
        for iteration in scenario.get("iterations", []):
            lines.append(
                f"- Iteration {iteration.get('index')}: status `{iteration.get('status')}`, "
                f"wall `{_fmt(iteration.get('wall_time_ms'))}` ms, "
                f"startup `{_fmt(iteration.get('startup', {}).get('TotalTime'))}` ms, "
                f"log `{iteration.get('logcat')}`"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def compare_reports(current: Dict[str, Any], baseline: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    baseline_by_name = {
        item.get("name"): item for item in baseline.get("summary", {}).get("scenarios", [])
    }
    status = "pass"
    for current_item in current.get("summary", {}).get("scenarios", []):
        name = current_item.get("name")
        base_item = baseline_by_name.get(name)
        if not base_item:
            findings.append({"status": "warn", "scenario": name, "metric": "scenario", "message": "No baseline scenario."})
            status = _worse(status, "warn")
            continue
        status = _compare_metric(
            findings,
            status,
            name,
            "wall_time_ms.p90",
            _nested(current_item, "wall_time_ms", "p90"),
            _nested(base_item, "wall_time_ms", "p90"),
            warn_ratio=thresholds.get("startup_p90_warn_ratio", 0.15),
            fail_ratio=thresholds.get("scenario_p90_fail_ratio", 0.20),
        )
        status = _compare_metric(
            findings,
            status,
            name,
            "startup_total_time_ms.p90",
            _nested(current_item, "startup_total_time_ms", "p90"),
            _nested(base_item, "startup_total_time_ms", "p90"),
            warn_ratio=thresholds.get("startup_p90_warn_ratio", 0.15),
            fail_ratio=thresholds.get("startup_p90_fail_ratio", 0.25),
        )
        stability = current_item.get("stability", {})
        if thresholds.get("crash_or_anr_fail", True) and (stability.get("crash", 0) or stability.get("anr", 0)):
            findings.append(
                {
                    "status": "fail",
                    "scenario": name,
                    "metric": "stability",
                    "message": f"Crash/ANR detected: crash={stability.get('crash', 0)}, anr={stability.get('anr', 0)}",
                }
            )
            status = "fail"
    return {
        "status": status,
        "current_run_id": current.get("run_id"),
        "baseline_run_id": baseline.get("run_id"),
        "findings": findings,
    }


def _compare_metric(
    findings: List[Dict[str, Any]],
    status: str,
    scenario: str,
    metric: str,
    current: Optional[float],
    baseline: Optional[float],
    warn_ratio: float,
    fail_ratio: float,
) -> str:
    if current is None or baseline in (None, 0):
        return status
    delta_ratio = (current - baseline) / baseline
    if delta_ratio >= fail_ratio:
        findings.append(_finding("fail", scenario, metric, current, baseline, delta_ratio))
        return "fail"
    if delta_ratio >= warn_ratio:
        findings.append(_finding("warn", scenario, metric, current, baseline, delta_ratio))
        return _worse(status, "warn")
    return status


def _finding(status: str, scenario: str, metric: str, current: float, baseline: float, delta_ratio: float) -> Dict[str, Any]:
    return {
        "status": status,
        "scenario": scenario,
        "metric": metric,
        "current": current,
        "baseline": baseline,
        "delta_ratio": delta_ratio,
    }


def _nested(mapping: Dict[str, Any], *keys: str) -> Any:
    value: Any = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _worse(left: str, right: str) -> str:
    rank = {"pass": 0, "warn": 1, "fail": 2}
    return left if rank[left] >= rank[right] else right


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)
