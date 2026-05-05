from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .adb import Adb


@dataclass
class UiNode:
    text: str
    content_desc: str
    resource_id: str
    class_name: str
    bounds: str
    clickable: bool

    @property
    def center(self) -> Tuple[int, int]:
        left, top, right, bottom = parse_bounds(self.bounds)
        return int((left + right) / 2), int((top + bottom) / 2)


class UiAutomator:
    def __init__(self, adb: Adb, output_dir: Path):
        self.adb = adb
        self.output_dir = output_dir

    def dump(self, name: str = "window") -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        remote = f"/sdcard/phone2app-{name}.xml"
        local = self.output_dir / f"{name}.xml"
        self.adb.shell(f"uiautomator dump {remote}", timeout=20, check=False)
        self.adb.pull(remote, local, timeout=20)
        self.adb.remove_remote(remote)
        return local

    def nodes(self, name: str = "window") -> List[UiNode]:
        return parse_ui_nodes(self.dump(name))

    def find(self, selector: Dict[str, str], timeout_seconds: float = 8.0, interval_seconds: float = 0.5) -> UiNode:
        deadline = time.time() + timeout_seconds
        last_nodes: List[UiNode] = []
        while time.time() <= deadline:
            last_nodes = self.nodes("window")
            for node in last_nodes:
                if node_matches(node, selector):
                    return node
            time.sleep(interval_seconds)
        raise LookupError(f"UI node not found: {selector}. Visible nodes: {summarize_nodes(last_nodes)}")

    def tap(self, selector: Dict[str, str], timeout_seconds: float = 8.0) -> UiNode:
        node = self.find(selector, timeout_seconds=timeout_seconds)
        x, y = node.center
        self.adb.shell(f"input tap {x} {y}", timeout=10)
        return node

    def input_text(self, value: str) -> None:
        escaped = value.replace(" ", "%s").replace("&", "\\&")
        self.adb.shell(f"input text {escaped}", timeout=10)


def parse_ui_nodes(path: Path) -> List[UiNode]:
    root = ET.parse(path).getroot()
    nodes: List[UiNode] = []
    for node in root.iter("node"):
        nodes.append(
            UiNode(
                text=node.attrib.get("text", ""),
                content_desc=node.attrib.get("content-desc", ""),
                resource_id=node.attrib.get("resource-id", ""),
                class_name=node.attrib.get("class", ""),
                bounds=node.attrib.get("bounds", ""),
                clickable=node.attrib.get("clickable", "false") == "true",
            )
        )
    return nodes


def node_matches(node: UiNode, selector: Dict[str, str]) -> bool:
    if "text" in selector and node.text != selector["text"]:
        return False
    if "text_contains" in selector and selector["text_contains"] not in node.text:
        return False
    if "content_desc" in selector and node.content_desc != selector["content_desc"]:
        return False
    if "content_desc_contains" in selector and selector["content_desc_contains"] not in node.content_desc:
        return False
    if "resource_id" in selector and node.resource_id != selector["resource_id"]:
        return False
    if "class_name" in selector and node.class_name != selector["class_name"]:
        return False
    return True


def parse_bounds(bounds: str) -> Tuple[int, int, int, int]:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Invalid Android bounds: {bounds!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def selector_from_step(step: Dict[str, object]) -> Dict[str, str]:
    action = str(step.get("action"))
    value = str(step.get("value", ""))
    if action in ("tap_text", "assert_text"):
        return {"text": value}
    if action == "tap_text_contains":
        return {"text_contains": value}
    if action in ("tap_content_desc", "tap_accessibility_id", "assert_content_desc"):
        return {"content_desc": value}
    if action in ("tap_content_desc_contains", "assert_content_desc_contains"):
        return {"content_desc_contains": value}
    if action == "tap_resource_id":
        return {"resource_id": value}
    if action == "assert_text_contains":
        return {"text_contains": value}
    raise ValueError(f"Cannot build selector for action: {action}")


def summarize_nodes(nodes: Iterable[UiNode]) -> str:
    visible = []
    for node in nodes:
        label = node.text or node.content_desc or node.resource_id
        if label:
            visible.append(label)
    return ", ".join(visible[:20])
