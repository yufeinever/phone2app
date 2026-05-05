from pathlib import Path

from phone2app.adb import parse_am_start_w, parse_gfxinfo, parse_meminfo_pss_kb
from phone2app.logs import scan_stability_events


def test_parse_am_start_w():
    output = """
Status: ok
ThisTime: 123
TotalTime: 456
WaitTime: 789
"""
    assert parse_am_start_w(output) == {"ThisTime": 123, "TotalTime": 456, "WaitTime": 789}


def test_parse_meminfo_total_pss():
    output = """
 App Summary
                       Pss(KB)
 TOTAL                  42123    40000
"""
    assert parse_meminfo_pss_kb(output) == 42123


def test_parse_gfxinfo_summary():
    output = """
Stats since: 123
Total frames rendered: 100
Janky frames: 4 (4.00%)
90th percentile: 12ms
95th percentile: 18ms
99th percentile: 33ms
"""
    assert parse_gfxinfo(output) == {
        "total_frames": 100.0,
        "janky_frames": 4.0,
        "janky_percent": 4.0,
        "frame_p90_ms": 12.0,
        "frame_p95_ms": 18.0,
        "frame_p99_ms": 33.0,
    }


def test_scan_stability_events(tmp_path: Path):
    log = tmp_path / "logcat.log"
    log.write_text(
        "01-01 AndroidRuntime FATAL EXCEPTION: main\n"
        "01-01 ActivityManager ANR in com.example\n",
        encoding="utf-8",
    )
    events = scan_stability_events(log)
    assert [event.kind for event in events] == ["crash", "anr"]


def test_androidruntime_uiautomator_lines_are_not_crashes(tmp_path: Path):
    log = tmp_path / "logcat.log"
    log.write_text(
        "05-02 13:24:21.680 29239 29239 D AndroidRuntime: >>>>>> START com.android.internal.os.RuntimeInit uid 2000 <<<<<<\n"
        "05-02 13:24:22.874 29239 29239 D AndroidRuntime: Shutting down VM\n",
        encoding="utf-8",
    )
    assert scan_stability_events(log) == []
