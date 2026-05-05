from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

from .locators import Locator


@dataclass(frozen=True)
class SwipePlan:
    start_x_ratio: float
    start_y_ratio: float
    end_x_ratio: float
    end_y_ratio: float
    duration_ms: int = 450

    def to_pixels(self, width: int, height: int) -> Tuple[int, int, int, int, int]:
        return (
            int(width * self.start_x_ratio),
            int(height * self.start_y_ratio),
            int(width * self.end_x_ratio),
            int(height * self.end_y_ratio),
            self.duration_ms,
        )


SWIPE_FEATURES_LEFT = SwipePlan(0.86, 0.90, 0.18, 0.90)
SWIPE_FEATURES_RIGHT = SwipePlan(0.18, 0.90, 0.86, 0.90)


class BasePage:
    def __init__(self, driver: Any, explicit_wait_seconds: float = 15):
        self.driver = driver
        self.explicit_wait_seconds = explicit_wait_seconds

    def find(self, locator: Locator):
        return self.driver.find_element(*locator.as_tuple())

    def find_all(self, locator: Locator):
        return self.driver.find_elements(*locator.as_tuple())

    def exists(self, locator: Locator) -> bool:
        try:
            self.find(locator)
            return True
        except Exception:
            return False

    def wait_for(self, locator: Locator, timeout_seconds: Optional[float] = None):
        deadline = time.time() + (timeout_seconds or self.explicit_wait_seconds)
        last_error: Optional[Exception] = None
        while time.time() <= deadline:
            try:
                return self.find(locator)
            except Exception as exc:
                last_error = exc
                time.sleep(0.4)
        raise TimeoutError(f"Element not found: {locator}") from last_error

    def tap(self, locator: Locator, timeout_seconds: Optional[float] = None) -> None:
        self.wait_for(locator, timeout_seconds=timeout_seconds).click()

    def page_source(self) -> str:
        return self.driver.page_source

    def screenshot(self, path: str) -> None:
        self.driver.save_screenshot(path)

    def window_size(self) -> Tuple[int, int]:
        size = self.driver.get_window_size()
        return int(size["width"]), int(size["height"])

    def swipe_plan(self, plan: SwipePlan) -> None:
        width, height = self.window_size()
        self.driver.swipe(*plan.to_pixels(width, height))

    def back(self) -> None:
        self.driver.back()
