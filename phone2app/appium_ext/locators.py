from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Locator:
    by: str
    value: str

    def as_tuple(self) -> Tuple[str, str]:
        return self.by, self.value


def accessibility(label: str) -> Locator:
    return Locator("accessibility id", label)


def text_exact(value: str) -> Locator:
    return Locator("xpath", f"//*[@text={xpath_literal(value)}]")


def text_contains(value: str) -> Locator:
    return Locator("xpath", f"//*[contains(@text, {xpath_literal(value)})]")


def desc_contains(value: str) -> Locator:
    return Locator("xpath", f"//*[contains(@content-desc, {xpath_literal(value)})]")


def class_name(value: str) -> Locator:
    return Locator("class name", value)


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in parts) + ")"
