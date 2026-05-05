from __future__ import annotations

import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import uiautomator2 as u2


SERIAL = os.environ.get("ANDROID_SERIAL", "")
PACKAGE = "com.larus.nova"
MAIN_ACTIVITY = "com.larus.home.impl.MainActivity"
LAUNCHER = "com.larus.nova/com.larus.home.impl.alias.AliasActivity1"
_U2_DEVICE = None


def adb_cmd(args: list[str]) -> list[str]:
    return ["adb", *(['-s', SERIAL] if SERIAL else []), *args]


@dataclass
class Node:
    index: int
    package: str
    cls: str
    resource_id: str
    text: str
    desc: str
    bounds: tuple[int, int, int, int]
    clickable: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2

    @property
    def label(self) -> str:
        return self.text or self.desc or self.resource_id


def adb(args: list[str], timeout: int = 30, text: bool = True) -> str | bytes:
    cmd = adb_cmd(args)
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
    )
    if result.returncode != 0:
        err = result.stderr if text else result.stderr.decode("utf-8", "replace")
        out = result.stdout if text else result.stdout.decode("utf-8", "replace")
        raise RuntimeError(f"{' '.join(cmd)} failed\nstdout={out}\nstderr={err}")
    return result.stdout


def adb_no_raise(args: list[str], timeout: int = 30) -> str:
    try:
        return str(adb(args, timeout=timeout, text=True))
    except Exception as exc:
        return f"ERROR: {exc}"


def u2_device():
    global _U2_DEVICE
    if _U2_DEVICE is None:
        _U2_DEVICE = u2.connect_usb(SERIAL) if SERIAL else u2.connect_usb()
    return _U2_DEVICE


def launch_app() -> None:
    wake_and_unlock()
    adb(["shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"], timeout=30)
    time.sleep(1.2)


def force_stop_app() -> None:
    adb(["shell", "am", "force-stop", PACKAGE], timeout=15)
    time.sleep(0.8)


def tap_xy(x: int, y: int) -> None:
    adb(["shell", "input", "tap", str(x), str(y)], timeout=10)


def tap_node(node: Node) -> None:
    x, y = node.center
    tap_xy(x, y)


def press_back() -> None:
    adb(["shell", "input", "keyevent", "BACK"], timeout=10)


def wake_and_unlock() -> None:
    adb_no_raise(["shell", "input", "keyevent", "WAKEUP"], timeout=10)
    time.sleep(0.2)
    focus = foreground_summary()
    if "StatusBar" in focus or "keyguard" in focus.lower() or "Keyguard" in focus:
        adb_no_raise(["shell", "input", "swipe", "540", "1900", "540", "500", "250"], timeout=10)
        time.sleep(0.8)


def screencap(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = adb(["exec-out", "screencap", "-p"], timeout=20, text=False)
    path.write_bytes(bytes(data))


def foreground_summary() -> str:
    text = adb_no_raise(["shell", "dumpsys", "window"], timeout=20)
    lines = []
    for line in text.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            lines.append(line.strip())
    return "\n".join(lines[:4])


def is_doubao_foreground() -> bool:
    return PACKAGE in foreground_summary()


def ensure_app_foreground() -> None:
    if not is_doubao_foreground():
        launch_app()


def parse_bounds(raw: str) -> tuple[int, int, int, int]:
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if len(nums) != 4:
        return (0, 0, 0, 0)
    return tuple(nums)  # type: ignore[return-value]


def parse_xml(path: Path) -> list[Node]:
    root = ET.parse(path).getroot()
    nodes: list[Node] = []
    for idx, elem in enumerate(root.iter("node")):
        nodes.append(
            Node(
                index=idx,
                package=elem.attrib.get("package", ""),
                cls=elem.attrib.get("class", ""),
                resource_id=elem.attrib.get("resource-id", ""),
                text=elem.attrib.get("text", ""),
                desc=elem.attrib.get("content-desc", ""),
                bounds=parse_bounds(elem.attrib.get("bounds", "")),
                clickable=elem.attrib.get("clickable", "false") == "true",
                enabled=elem.attrib.get("enabled", "false") == "true",
            )
        )
    return nodes


def dump_xml(path: Path) -> list[Node]:
    path.parent.mkdir(parents=True, exist_ok=True)
    xml = u2_device().dump_hierarchy(compressed=False, pretty=True)
    if not xml.strip():
        raise RuntimeError("uiautomator2 dump_hierarchy returned empty XML")
    path.write_text(xml, encoding="utf-8")
    return parse_xml(path)


def node_json(nodes: Iterable[Node]) -> list[dict[str, object]]:
    return [asdict(node) for node in nodes if node.resource_id or node.text or node.desc]


def has_app_nodes(nodes: Iterable[Node]) -> bool:
    return any(node.package == PACKAGE for node in nodes)


def find_by_id(nodes: Iterable[Node], suffix: str) -> Node | None:
    for node in nodes:
        if node.resource_id.endswith(suffix):
            return node
    return None


def find_input(nodes: Iterable[Node]) -> Node | None:
    return find_by_id(nodes, ":id/input_text")


def find_send(nodes: Iterable[Node]) -> Node | None:
    return find_by_id(nodes, ":id/action_send")


def find_back_or_sidebar(nodes: Iterable[Node]) -> Node | None:
    return find_by_id(nodes, ":id/back_icon")


def find_create_conversation(nodes: Iterable[Node]) -> Node | None:
    return find_by_id(nodes, ":id/side_bar_create_conversation")


def page_text(nodes: Iterable[Node]) -> str:
    seen: set[str] = set()
    parts: list[str] = []
    for node in nodes:
        if node.package and node.package != PACKAGE:
            continue
        value = (node.text or node.desc).strip()
        if value and value not in seen:
            seen.add(value)
            parts.append(value)
    return "\n".join(parts)


def capture_state(out_dir: Path, prefix: str) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{prefix}.png"
    xml = out_dir / f"{prefix}.xml"
    nodes = dump_xml(xml)
    screencap(png)
    node_path = out_dir / f"{prefix}.nodes.json"
    node_path.write_text(json.dumps(node_json(nodes), ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "screenshot": str(png),
        "xml": str(xml),
        "nodes": str(node_path),
        "foreground": foreground_summary(),
        "text": page_text(nodes),
    }


def is_loading(nodes: Iterable[Node]) -> bool:
    return any(
        node.resource_id.endswith(":id/v_dot1")
        or node.resource_id.endswith(":id/v_dot2")
        or node.resource_id.endswith(":id/v_dot3")
        for node in nodes
    )


def has_answer_actions(nodes: Iterable[Node]) -> bool:
    action_suffixes = (
        ":id/msg_action_copy",
        ":id/msg_action_re_tts",
        ":id/msg_action_regenerate",
    )
    return any(any(node.resource_id.endswith(suffix) for suffix in action_suffixes) for node in nodes)


def open_new_chat(out_dir: Path, prefix: str) -> list[Node]:
    nodes = dump_xml(out_dir / f"{prefix}_before.xml")
    if not any(node.package == PACKAGE for node in nodes):
        ensure_app_foreground()
        nodes = dump_xml(out_dir / f"{prefix}_after_launch.xml")
    create = find_create_conversation(nodes)
    if not create:
        back = find_back_or_sidebar(nodes)
        if not back:
            raise RuntimeError("未找到豆包侧栏/返回入口 back_icon")
        tap_node(back)
        time.sleep(0.8)
        nodes = dump_xml(out_dir / f"{prefix}_sidebar.xml")
        create = find_create_conversation(nodes)
    if not create:
        raise RuntimeError("未找到豆包创建新对话按钮 side_bar_create_conversation")
    tap_node(create)
    time.sleep(1.0)
    nodes = dump_xml(out_dir / f"{prefix}_after.xml")
    screencap(out_dir / f"{prefix}_after.png")
    if not find_input(nodes):
        raise RuntimeError("新建对话后未找到豆包输入框 input_text")
    return nodes


def recover_to_text_chat(out_dir: Path, prefix: str) -> list[Node]:
    nodes = dump_xml(out_dir / f"{prefix}_before.xml")
    if not any(node.package == PACKAGE for node in nodes):
        press_back()
        time.sleep(0.4)
        ensure_app_foreground()
        nodes = dump_xml(out_dir / f"{prefix}_after_launch.xml")
    if find_create_conversation(nodes):
        press_back()
        time.sleep(0.5)
        nodes = dump_xml(out_dir / f"{prefix}_after_close_sidebar.xml")
    edit = find_input(nodes)
    if edit:
        tap_node(edit)
        time.sleep(0.2)
        return dump_xml(out_dir / f"{prefix}_after_focus.xml")
    action_input = find_by_id(nodes, ":id/action_input")
    if action_input:
        tap_node(action_input)
        time.sleep(0.5)
        nodes = dump_xml(out_dir / f"{prefix}_after_keyboard.xml")
        if find_input(nodes):
            return nodes
    raise RuntimeError("未恢复到豆包文本输入态 input_text")
