from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from .base_page import BasePage, SWIPE_FEATURES_LEFT, SWIPE_FEATURES_RIGHT
from .input_providers import AppiumTextInput, TextInputProvider
from .locators import Locator, accessibility, class_name, desc_contains, text_exact


class ChatPage(BasePage):
    title = desc_contains("AI")
    input_box = class_name("android.widget.EditText")
    voice_prompt = text_exact("点击说话")

    def wait_loaded(self) -> "ChatPage":
        self.wait_for(self.title)
        return self

    def input_element(self):
        return self.wait_for(self.input_box)

    def enter_text(self, text: str, provider: Optional[TextInputProvider] = None) -> None:
        provider = provider or AppiumTextInput()
        element = self.input_element()
        provider.clear_text(element)
        provider.input_text(element, text)

    def send_current_text(self) -> None:
        element = self.input_element()
        rect = element.rect
        candidates = self.driver.find_elements("class name", "android.widget.ImageView")
        same_row = []
        center_y = rect["y"] + rect["height"] / 2
        for item in candidates:
            ir = item.rect
            item_center_y = ir["y"] + ir["height"] / 2
            if ir["x"] >= rect["x"] + rect["width"] - 20 and abs(item_center_y - center_y) <= 180:
                same_row.append(item)
        if not same_row:
            raise LookupError("No send button candidate found near input box.")
        max(same_row, key=lambda item: item.rect["x"] + item.rect["width"]).click()

    def ask(self, text: str, provider: Optional[TextInputProvider] = None) -> None:
        self.enter_text(text, provider=provider)
        self.send_current_text()

    def switch_to_voice_input(self) -> None:
        self._right_side_button(offset_from_right=2).click()
        self.wait_for(self.voice_prompt, timeout_seconds=5)

    def start_voice_capture(self) -> None:
        self.wait_for(self.voice_prompt).click()

    def open_attachment_sheet(self) -> "AttachmentSheet":
        self._right_side_button(offset_from_right=1).click()
        return AttachmentSheet(self.driver, self.explicit_wait_seconds).wait_loaded()

    def feature_carousel(self) -> "FeatureCarousel":
        return FeatureCarousel(self.driver, self.explicit_wait_seconds)

    def open_av_call(self) -> "AvCallPage":
        self.feature_carousel().tap_feature("音视频通话")
        return AvCallPage(self.driver, self.explicit_wait_seconds).wait_loaded()

    def _right_side_button(self, offset_from_right: int):
        candidates = self.driver.find_elements("class name", "android.widget.ImageView")
        bottom = sorted(candidates, key=lambda item: (item.rect["y"], item.rect["x"]))
        if not bottom:
            raise LookupError("No ImageView buttons found.")
        by_y = sorted(bottom, key=lambda item: item.rect["y"], reverse=True)
        row_y = by_y[0].rect["y"]
        row = [item for item in candidates if abs(item.rect["y"] - row_y) <= 80]
        row = sorted(row, key=lambda item: item.rect["x"], reverse=True)
        if len(row) < offset_from_right:
            raise LookupError(f"Cannot find right-side button offset {offset_from_right}.")
        return row[offset_from_right - 1]


class FeatureCarousel(BasePage):
    DEFAULT_FEATURE_LABELS = ("Voice Chat", "音视频通话", "AI Writing", "Podcast")

    def visible_items(self) -> List[str]:
        labels = []
        for item in self.driver.find_elements("class name", "android.widget.ImageView"):
            label = item.get_attribute("contentDescription") or item.get_attribute("content-desc") or ""
            if label in self.DEFAULT_FEATURE_LABELS:
                labels.append(label)
        return labels

    def tap_feature(self, label: str) -> None:
        self.scroll_to(label)
        self.tap(accessibility(label), timeout_seconds=5)

    def scroll_to(self, label: str, max_swipes: int = 4) -> None:
        if self.exists(accessibility(label)):
            return
        for _ in range(max_swipes):
            self.swipe_left()
            if self.exists(accessibility(label)):
                return
        for _ in range(max_swipes):
            self.swipe_right()
            if self.exists(accessibility(label)):
                return
        raise TimeoutError(f"Feature not visible in carousel: {label}")

    def swipe_left(self) -> None:
        self.swipe_plan(SWIPE_FEATURES_LEFT)

    def swipe_right(self) -> None:
        self.swipe_plan(SWIPE_FEATURES_RIGHT)


class AttachmentSheet(BasePage):
    def wait_loaded(self) -> "AttachmentSheet":
        self.wait_for(desc_contains("上传附件"), timeout_seconds=5)
        return self

    def choose_image(self) -> None:
        self.tap(accessibility("图片"), timeout_seconds=5)

    def choose_file(self) -> "SystemFilePickerPage":
        self.tap(accessibility("文件"), timeout_seconds=5)
        return SystemFilePickerPage(self.driver, self.explicit_wait_seconds).wait_loaded()

    def cancel(self) -> None:
        self.tap(accessibility("取消"), timeout_seconds=5)


class SystemFilePickerPage(BasePage):
    def wait_loaded(self) -> "SystemFilePickerPage":
        self.wait_for(text_exact("最近"), timeout_seconds=8)
        return self

    def open_category(self, label: str) -> None:
        self.tap(text_exact(label), timeout_seconds=5)

    def tap_file_by_name_contains(self, name_part: str) -> None:
        self.tap(desc_contains(name_part), timeout_seconds=8)


class AvCallPage(BasePage):
    def wait_loaded(self) -> "AvCallPage":
        self.wait_for(text_exact("字幕"), timeout_seconds=10)
        return self

    def toggle_subtitles(self) -> None:
        self.tap(text_exact("字幕"), timeout_seconds=5)

    def exit_call(self) -> None:
        width, height = self.window_size()
        self.driver.tap([(int(width * 0.842), int(height * 0.936))])

    def microphone_button(self):
        width, height = self.window_size()
        return int(width * 0.386), int(height * 0.936)
