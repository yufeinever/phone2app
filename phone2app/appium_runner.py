from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


class AppiumUnavailable(RuntimeError):
    pass


@dataclass
class StepOutcome:
    action: str
    elapsed_ms: float
    ok: bool
    detail: str = ""


class AppiumScenarioRunner:
    def __init__(
        self,
        server_url: str,
        capabilities: Dict[str, Any],
        package: str,
        activity: Optional[str],
        serial: Optional[str],
    ):
        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
        except ImportError as exc:
            raise AppiumUnavailable(
                "Appium Python client is not installed. Run: python -m pip install '.[appium]'"
            ) from exc

        caps = dict(capabilities)
        caps.setdefault("platformName", "Android")
        caps.setdefault("automationName", "UiAutomator2")
        caps.setdefault("appPackage", package)
        if activity:
            caps.setdefault("appActivity", activity)
        if serial:
            caps.setdefault("udid", serial)
        self.webdriver = webdriver
        self.options = UiAutomator2Options().load_capabilities(caps)
        self.server_url = server_url
        self.driver = None

    def __enter__(self) -> "AppiumScenarioRunner":
        self.driver = self.webdriver.Remote(self.server_url, options=self.options)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.driver:
            self.driver.quit()

    def run_steps(self, steps: Iterable[Dict[str, Any]]) -> List[StepOutcome]:
        if self.driver is None:
            raise RuntimeError("Appium driver is not started.")
        outcomes: List[StepOutcome] = []
        for step in steps:
            action = step.get("action")
            started = time.perf_counter()
            detail = ""
            ok = True
            try:
                if action == "wait":
                    time.sleep(float(step.get("seconds", 1)))
                elif action == "tap_text":
                    value = _required_value(step)
                    self.driver.find_element("xpath", f"//*[@text={_xpath_literal(value)}]").click()
                    detail = value
                elif action == "tap_accessibility_id":
                    value = _required_value(step)
                    self.driver.find_element("accessibility id", value).click()
                    detail = value
                elif action == "tap_xpath":
                    value = _required_value(step)
                    self.driver.find_element("xpath", value).click()
                    detail = value
                elif action == "assert_text":
                    value = _required_value(step)
                    self.driver.find_element("xpath", f"//*[@text={_xpath_literal(value)}]")
                    detail = value
                elif action == "press_back":
                    self.driver.back()
                elif action == "launch":
                    # adb handles launch so startup timing can be captured consistently.
                    pass
                else:
                    raise ValueError(f"Unsupported Appium action: {action!r}")
            except Exception as exc:  # selenium exceptions should be kept in report details.
                ok = False
                detail = str(exc)
            elapsed_ms = (time.perf_counter() - started) * 1000
            outcomes.append(StepOutcome(action=str(action), elapsed_ms=elapsed_ms, ok=ok, detail=detail))
            if not ok:
                break
        return outcomes


def needs_appium(steps: Iterable[Dict[str, Any]]) -> bool:
    adb_only = {
        "launch",
        "wait",
        "tap_text",
        "tap_text_contains",
        "tap_content_desc",
        "tap_content_desc_contains",
        "tap_accessibility_id",
        "tap_resource_id",
        "assert_content_desc",
        "assert_content_desc_contains",
        "assert_text",
        "assert_text_contains",
        "input_text",
        "press_back",
        "tap_xy",
    }
    return any(step.get("action") not in adb_only for step in steps)


def _required_value(step: Dict[str, Any]) -> str:
    value = step.get("value")
    if not value:
        raise ValueError(f"Step {step!r} requires a non-empty value.")
    return str(value)


def _xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in parts) + ")"
