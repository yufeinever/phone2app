from phone2app.runner import _overall_status


def test_overall_status_fails_when_iteration_fails():
    assert _overall_status([{"iterations": [{"status": "fail"}]}]) == "fail"
