from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from phone2app.config import load_config


class AppiumDependencyError(RuntimeError):
    pass


def load_appium_settings(path: str = "configs/appium.yaml") -> Dict[str, Any]:
    data = load_config(path)
    data.setdefault("server_url", "http://127.0.0.1:4723")
    data.setdefault("implicit_wait_seconds", 2)
    data.setdefault("explicit_wait_seconds", 15)
    data.setdefault("capabilities", {})
    return data


def create_driver(settings: Dict[str, Any], serial: Optional[str] = None):
    try:
        from appium import webdriver
        from appium.options.android import UiAutomator2Options
    except ImportError as exc:
        raise AppiumDependencyError(
            "Appium Python client is not installed. Install with: "
            "python -m pip install Appium-Python-Client selenium"
        ) from exc

    caps = dict(settings.get("capabilities") or {})
    if serial:
        caps["udid"] = serial
    caps.setdefault("platformName", "Android")
    caps.setdefault("automationName", "UiAutomator2")
    options = UiAutomator2Options().load_capabilities(caps)
    driver = webdriver.Remote(settings["server_url"], options=options)
    driver.implicitly_wait(float(settings.get("implicit_wait_seconds", 2)))
    return driver


@contextmanager
def appium_session(config_path: str = "configs/appium.yaml", serial: Optional[str] = None) -> Iterator[Any]:
    driver = create_driver(load_appium_settings(config_path), serial=serial)
    try:
        yield driver
    finally:
        driver.quit()
