from phone2app.reporting import compare_reports, percentile, summarize


def test_percentile_interpolates():
    assert percentile([100, 200, 300, 400, 500], 90) == 460


def test_summarize_empty():
    assert summarize([])["count"] == 0
    assert summarize([])["p90"] is None


def test_compare_reports_marks_regression_fail():
    baseline = {
        "run_id": "base",
        "summary": {
            "scenarios": [
                {"name": "cold_start", "wall_time_ms": {"p90": 1000}, "startup_total_time_ms": {"p90": 1000}, "stability": {}}
            ]
        },
    }
    current = {
        "run_id": "cur",
        "summary": {
            "scenarios": [
                {"name": "cold_start", "wall_time_ms": {"p90": 1300}, "startup_total_time_ms": {"p90": 1100}, "stability": {}}
            ]
        },
    }
    result = compare_reports(current, baseline, {"scenario_p90_fail_ratio": 0.2, "startup_p90_fail_ratio": 0.25})
    assert result["status"] == "fail"
    assert result["findings"][0]["metric"] == "wall_time_ms.p90"
