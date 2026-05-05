from __future__ import annotations

import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import uiautomator2 as u2


SERIAL = os.environ.get("ANDROID_SERIAL", "")
PACKAGE = "com.jiutian.yidonglingxi"
LAUNCH_ACTIVITY = "com.aspire.jiutian.activity.SplashActivity"
CHAT_ACTIVITY = "com.aspire.jiutian.rebuild.activity.ChatActivity"
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


def tap_xy(x: int, y: int) -> None:
    adb(["shell", "input", "tap", str(x), str(y)], timeout=10)


def tap_node(node: Node) -> None:
    x, y = node.center
    tap_xy(x, y)


def press_back() -> None:
    adb(["shell", "input", "keyevent", "BACK"], timeout=10)


def foreground() -> str:
    return adb_no_raise(["shell", "dumpsys", "window"], timeout=20)


def foreground_summary() -> str:
    text = foreground()
    matches = []
    for line in text.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            matches.append(line.strip())
    return "\n".join(matches[:4])


def launch_app() -> None:
    adb(
        ["shell", "monkey", "-p", PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"],
        timeout=30,
    )
    time.sleep(1.2)


def force_stop_app() -> None:
    adb(["shell", "am", "force-stop", PACKAGE], timeout=15)
    time.sleep(0.8)


def screencap(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = adb(["exec-out", "screencap", "-p"], timeout=20, text=False)
    path.write_bytes(bytes(data))


def u2_device():
    global _U2_DEVICE
    if _U2_DEVICE is None:
        _U2_DEVICE = u2.connect_usb(SERIAL) if SERIAL else u2.connect_usb()
    return _U2_DEVICE


def dump_xml(path: Path, retries: int = 2) -> list[Node]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        xml = u2_device().dump_hierarchy(compressed=False, pretty=True)
        if xml.strip():
            path.write_text(xml, encoding="utf-8")
            return parse_xml(path)
    except Exception:
        pass

    last_error = ""
    for attempt in range(retries + 1):
        result = subprocess.run(
            adb_cmd(["shell", "uiautomator", "dump", "/sdcard/window.xml"]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        last_error = (result.stdout or "") + (result.stderr or "")
        if result.returncode == 0 or "UI hierchary dumped" in last_error or "UI hierarchy dumped" in last_error:
            break
        time.sleep(0.5 + attempt * 0.5)
    pull = subprocess.run(
        adb_cmd(["pull", "/sdcard/window.xml", str(path)]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if pull.returncode != 0 or not path.exists():
        raise RuntimeError(f"uiautomator dump failed: {last_error}\npull={pull.stdout}{pull.stderr}")
    return parse_xml(path)


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


def has_app_nodes(nodes: Iterable[Node]) -> bool:
    return any(node.package == PACKAGE for node in nodes)


def node_json(nodes: Iterable[Node]) -> list[dict[str, object]]:
    return [asdict(node) for node in nodes if node.resource_id or node.text or node.desc]


def find_by_id(nodes: Iterable[Node], suffix: str) -> Node | None:
    for node in nodes:
        if node.resource_id.endswith(suffix):
            return node
    return None


def find_text(nodes: Iterable[Node], needle: str) -> Node | None:
    for node in nodes:
        if needle in node.text or needle in node.desc:
            return node
    return None


def find_input(nodes: Iterable[Node]) -> Node | None:
    return find_by_id(nodes, ":id/et_input")


def find_send(nodes: Iterable[Node]) -> Node | None:
    for suffix in (":id/ll_txt_send", ":id/iv_send", ":id/btn_send"):
        node = find_by_id(nodes, suffix)
        if node:
            return node
    candidates = []
    for node in nodes:
        left, top, right, bottom = node.bounds
        if node.clickable and right > 900 and top > 1850:
            candidates.append(node)
    if candidates:
        return max(candidates, key=lambda n: (n.bounds[2], n.bounds[3]))
    return None


def classify_page(nodes: list[Node], focus: str | None = None) -> str:
    focus = focus or foreground_summary()
    text = page_text(nodes)
    if PACKAGE not in focus:
        return "wrong_or_unknown_app"
    if find_by_id(nodes, ":id/rl_new_chat") or "新建对话" in text and "自动播报" in text:
        return "config_menu_open"
    if "想要我怎么称呼你" in text or "修改昵称" in text or "关闭性格" in text:
        return "welcome_personality"
    if "点击说话" in text:
        return "voice_input"
    if find_input(nodes):
        return "text_chat"
    if "通话中" in text or "点击打断" in text:
        return "call_or_voice_session"
    if "助理技能" in text or "技能配置" in text:
        return "assist_config"
    return "unknown_mobile_lingxi"


def capture_state(run_dir: Path, name: str) -> dict[str, object]:
    png = run_dir / f"{name}.png"
    xml = run_dir / f"{name}.xml"
    screencap(png)
    nodes = dump_xml(xml)
    focus = foreground_summary()
    state = {
        "name": name,
        "time": datetime.now().isoformat(timespec="seconds"),
        "foreground": focus,
        "classification": classify_page(nodes, focus),
        "screenshot": str(png),
        "xml": str(xml),
        "visible_text": page_text(nodes),
        "nodes": node_json(nodes),
    }
    (run_dir / f"{name}.nodes.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state


def tap_text_mode_from_welcome(nodes: list[Node]) -> bool:
    for suffix in (":id/btn_chat_text", ":id/tv_chat_text"):
        node = find_by_id(nodes, suffix)
        if node:
            tap_node(node)
            time.sleep(0.8)
            return True
    tap_xy(725, 1976)
    time.sleep(0.8)
    return True


def close_config_menu_if_open(nodes: list[Node]) -> bool:
    if classify_page(nodes) == "config_menu_open":
        press_back()
        time.sleep(0.5)
        return True
    return False


def recover_to_text_chat(run_dir: Path, prefix: str = "recover") -> list[Node]:
    if PACKAGE not in foreground_summary():
        launch_app()
    nodes = dump_xml(run_dir / f"{prefix}_start.xml")
    if not has_app_nodes(nodes):
        # Long Web/search answers can make accessibility dumps time out and
        # return only SystemUI. Relaunch once, then prefer a fresh chat.
        force_stop_app()
        launch_app()
        nodes = dump_xml(run_dir / f"{prefix}_after_force_stop_relaunch.xml")
    state = classify_page(nodes)
    if state == "config_menu_open":
        press_back()
        time.sleep(0.5)
        nodes = dump_xml(run_dir / f"{prefix}_after_back_menu.xml")
        state = classify_page(nodes)
    if state == "welcome_personality":
        tap_text_mode_from_welcome(nodes)
        nodes = dump_xml(run_dir / f"{prefix}_after_welcome_text.xml")
        state = classify_page(nodes)
    if state == "voice_input":
        voice_or_keyboard = find_by_id(nodes, ":id/ll_record_voice")
        if voice_or_keyboard:
            tap_node(voice_or_keyboard)
        else:
            tap_xy(984, 2114)
        time.sleep(0.7)
        nodes = dump_xml(run_dir / f"{prefix}_after_voice_toggle.xml")
        state = classify_page(nodes)
    if state != "text_chat":
        launch_app()
        nodes = dump_xml(run_dir / f"{prefix}_after_relaunch.xml")
        state = classify_page(nodes)
        if state == "welcome_personality":
            tap_text_mode_from_welcome(nodes)
            nodes = dump_xml(run_dir / f"{prefix}_after_relaunch_welcome_text.xml")
    return nodes


def open_config_menu(run_dir: Path, prefix: str) -> list[Node]:
    nodes = recover_to_text_chat(run_dir, f"{prefix}_before_menu")
    button = find_by_id(nodes, ":id/img_header_conf")
    if button:
        tap_node(button)
    else:
        tap_xy(1018, 162)
    time.sleep(0.5)
    return dump_xml(run_dir / f"{prefix}_config_menu.xml")


def open_new_chat(run_dir: Path, prefix: str) -> list[Node]:
    nodes = open_config_menu(run_dir, prefix)
    row = find_by_id(nodes, ":id/rl_new_chat") or find_text(nodes, "新建对话")
    if row:
        tap_xy(*row.center)
    else:
        tap_xy(860, 526)
    time.sleep(0.9)
    return recover_to_text_chat(run_dir, f"{prefix}_after_new_chat")
