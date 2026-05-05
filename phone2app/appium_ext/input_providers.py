from __future__ import annotations

import base64
import subprocess
from dataclasses import dataclass
from typing import Any, Optional, Protocol


class TextInputProvider(Protocol):
    def input_text(self, element: Any, text: str) -> None:
        ...

    def clear_text(self, element: Any) -> None:
        ...


class AppiumTextInput:
    """Fallback input provider using Appium element APIs."""

    def input_text(self, element: Any, text: str) -> None:
        element.send_keys(text)

    def clear_text(self, element: Any) -> None:
        try:
            element.clear()
        except Exception:
            element.click()
            element.send_keys("")


@dataclass
class FastInputImeProvider:
    """Chinese/Unicode input provider backed by uiautomator2 FastInputIME.

    This provider is intentionally lazy: importing this module does not require
    uiautomator2. Install it only on machines that need Chinese input:
    `python -m pip install uiautomator2`.
    """

    serial: Optional[str] = None

    def _device(self):
        try:
            import uiautomator2 as u2
        except ImportError as exc:
            raise RuntimeError("uiautomator2 is required for FastInputIME input.") from exc
        return u2.connect(self.serial) if self.serial else u2.connect()

    def input_text(self, element: Any, text: str) -> None:
        element.click()
        device = self._device()
        device.set_fastinput_ime(True)
        device.send_keys(text, clear=False)

    def clear_text(self, element: Any) -> None:
        element.click()
        device = self._device()
        device.set_fastinput_ime(True)
        device.clear_text()


@dataclass
class BroadcastImeProvider:
    """Provider for a future self-hosted IME that accepts base64 broadcasts."""

    action: str = "phone2app.INPUT_TEXT"
    serial: Optional[str] = None

    def input_text(self, element: Any, text: str) -> None:
        element.click()
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._adb(["shell", "am", "broadcast", "-a", self.action, "--es", "text_base64", encoded])

    def clear_text(self, element: Any) -> None:
        element.click()
        self._adb(["shell", "input", "keyevent", "KEYCODE_MOVE_END", *["KEYCODE_DEL"] * 240])

    def _adb(self, args: list) -> None:
        cmd = ["adb"]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def build_input_provider(name: str, serial: Optional[str] = None) -> TextInputProvider:
    normalized = name.lower().strip()
    if normalized in ("appium", "send_keys"):
        return AppiumTextInput()
    if normalized in ("fastinput", "fastinput_ime", "uiautomator2"):
        return FastInputImeProvider(serial=serial)
    if normalized in ("broadcast_ime", "custom_ime"):
        return BroadcastImeProvider(serial=serial)
    raise ValueError(f"Unsupported input provider: {name}")
