from __future__ import annotations

import argparse
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import uiautomator2 as u2


ADB_DIR = Path(os.environ.get("ANDROID_PLATFORM_TOOLS", r"C:\Users\miaoyang\AppData\Local\Android\Sdk\platform-tools"))
if ADB_DIR.exists():
    os.environ["PATH"] = str(ADB_DIR) + os.pathsep + os.environ.get("PATH", "")

def default_serial() -> str:
    configured = os.environ.get("ANDROID_SERIAL", "").strip()
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["adb", "devices"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return ""
    devices: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices[0] if devices else ""


SERIAL = default_serial()
PROMPT = "来点音乐"

TEAM_PACKAGE = "com.chinamobile.eureka"
MOBILE_PACKAGE = "com.jiutian.yidonglingxi"
DOUBAO_PACKAGE = "com.larus.nova"


def start_screenrecord(case_dir: Path, prefix: str, time_limit_s: int = 2) -> dict[str, object]:
    remote = f"/sdcard/phone2app_{prefix}_{int(time.time() * 1000)}.mp4"
    local = case_dir / f"{prefix}.mp4"
    proc = subprocess.Popen(
        adb_cmd(["shell", "screenrecord", "--bit-rate", "4000000", "--time-limit", str(time_limit_s), remote]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.2)
    return {"proc": proc, "remote": remote, "local": local}


def stop_screenrecord(recording: dict[str, object]) -> Path:
    proc = recording["proc"]
    assert isinstance(proc, subprocess.Popen)
    remote = str(recording["remote"])
    local = Path(recording["local"])
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    time.sleep(0.4)
    adb(["pull", remote, str(local)], timeout=30)
    adb_no_raise(["shell", "rm", "-f", remote], timeout=10)
    return local


def stop_screenrecord_after(recording: dict[str, object], seconds: float) -> Path:
    time.sleep(seconds)
    return stop_screenrecord(recording)


def _gray_roi(frame, box: tuple[float, float, float, float]):
    import cv2

    height, width = frame.shape[:2]
    left = int(width * box[0])
    top = int(height * box[1])
    right = int(width * box[2])
    bottom = int(height * box[3])
    roi = frame[top:bottom, left:right]
    return cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)


def _diff_score(current, baseline) -> tuple[float, int]:
    import cv2

    diff = cv2.absdiff(current, baseline)
    changed = cv2.threshold(diff, 28, 255, cv2.THRESH_BINARY)[1]
    return float(diff.mean()), int(cv2.countNonZero(changed))


def analyze_team_visual_first_response(video_path: Path, case_dir: Path) -> dict[str, object] | None:
    import cv2

    capture = cv2.VideoCapture(str(video_path))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    ok, first_frame = capture.read()
    if not ok:
        return None

    # Trigger ROI watches the bottom/right input area where the typed prompt is sent.
    # Answer ROI watches the left/middle conversation area, excluding the user's blue bubble.
    trigger_base = _gray_roi(first_frame, (0.55, 0.76, 0.98, 0.98))
    answer_base = _gray_roi(first_frame, (0.03, 0.18, 0.78, 0.84))
    trigger_frame: int | None = None
    first_answer_frame: int | None = None
    trigger_debug: tuple[float, int] | None = None
    answer_debug: tuple[float, int] | None = None
    frame_index = 0
    trigger_png = case_dir / "visual_trigger_frame.png"
    answer_png = case_dir / "visual_first_answer_frame.png"

    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame_index += 1
        if trigger_frame is None:
            score = _diff_score(_gray_roi(frame, (0.55, 0.76, 0.98, 0.98)), trigger_base)
            if score[0] >= 4.5 or score[1] >= 7000:
                trigger_frame = frame_index
                trigger_debug = score
                cv2.imwrite(str(trigger_png), frame)
            continue
        if frame_index <= trigger_frame + max(1, int(fps * 0.06)):
            continue
        score = _diff_score(_gray_roi(frame, (0.03, 0.18, 0.78, 0.84)), answer_base)
        if score[0] >= 3.2 or score[1] >= 12000:
            first_answer_frame = frame_index
            answer_debug = score
            cv2.imwrite(str(answer_png), frame)
            break

    capture.release()
    if trigger_frame is None or first_answer_frame is None:
        return {
            "video": str(video_path),
            "fps": round(float(fps), 3),
            "trigger_frame": trigger_frame,
            "first_answer_frame": first_answer_frame,
            "status": "not_detected",
        }
    return {
        "video": str(video_path),
        "fps": round(float(fps), 3),
        "trigger_frame": trigger_frame,
        "first_answer_frame": first_answer_frame,
        "visual_first_response_time_ms": round((first_answer_frame - trigger_frame) * 1000 / fps, 1),
        "trigger_diff": {"mean": round(trigger_debug[0], 3), "pixels": trigger_debug[1]} if trigger_debug else None,
        "answer_diff": {"mean": round(answer_debug[0], 3), "pixels": answer_debug[1]} if answer_debug else None,
        "trigger_frame_png": str(trigger_png),
        "first_answer_frame_png": str(answer_png),
        "status": "ok",
    }


def start_minicap_capture(case_dir: Path, prefix: str, duration_s: float = 2.0) -> dict[str, object]:
    name = f"p2a_{prefix}_{int(time.time() * 1000)}"
    port = 17000 + (int(time.time() * 1000) % 1000)
    subprocess.run(adb_cmd(["forward", "--remove", f"tcp:{port}"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc = subprocess.Popen(
        adb_cmd(
            [
                "shell",
                "LD_LIBRARY_PATH=/data/local/tmp",
                "/data/local/tmp/minicap",
                "-n",
                name,
                "-P",
                "1080x2244@540x1122/0",
                "-S",
            ]
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.45)
    subprocess.run(
        adb_cmd(["forward", f"tcp:{port}", f"localabstract:{name}"]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    sock = socket.create_connection(("127.0.0.1", port), timeout=3)
    sock.settimeout(1)
    header = sock.recv(24)
    frames: list[dict[str, object]] = []
    stop_event = threading.Event()

    def read_exact(size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = sock.recv(size - len(chunks))
            if not chunk:
                raise EOFError("minicap socket closed")
            chunks.extend(chunk)
        return bytes(chunks)

    def reader() -> None:
        end_at = time.perf_counter() + duration_s
        while not stop_event.is_set() and time.perf_counter() < end_at:
            try:
                raw_size = read_exact(4)
                size = struct.unpack("<I", raw_size)[0]
                jpg = read_exact(size)
                frames.append({"t": time.perf_counter(), "jpg": jpg})
            except Exception:
                break

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return {
        "proc": proc,
        "sock": sock,
        "thread": thread,
        "stop_event": stop_event,
        "frames": frames,
        "port": port,
        "name": name,
        "header": list(header),
        "case_dir": case_dir,
    }


def stop_minicap_capture(capture: dict[str, object]) -> None:
    stop_event = capture["stop_event"]
    assert isinstance(stop_event, threading.Event)
    stop_event.set()
    thread = capture["thread"]
    assert isinstance(thread, threading.Thread)
    thread.join(timeout=2)
    sock = capture["sock"]
    assert isinstance(sock, socket.socket)
    try:
        sock.close()
    except Exception:
        pass
    proc = capture["proc"]
    assert isinstance(proc, subprocess.Popen)
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
    port = int(capture["port"])
    subprocess.run(adb_cmd(["forward", "--remove", f"tcp:{port}"]), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def analyze_team_minicap_visual(capture: dict[str, object], started: float, case_dir: Path) -> dict[str, object]:
    import cv2
    import numpy as np

    frames = list(capture.get("frames", []))
    if not frames:
        return {"status": "not_detected", "reason": "no_minicap_frames"}
    before = [frame for frame in frames if float(frame["t"]) <= started]
    after = [frame for frame in frames if float(frame["t"]) > started]
    if not before or not after:
        return {
            "status": "not_detected",
            "reason": "missing_before_or_after_frames",
            "frame_count": len(frames),
        }

    def decode(jpg: bytes):
        return cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)

    baseline = decode(bytes(before[-1]["jpg"]))
    answer_box = (0.03, 0.20, 0.74, 0.73)
    baseline_roi = _gray_roi(baseline, answer_box)
    baseline_path = case_dir / "visual_baseline_frame.jpg"
    cv2.imwrite(str(baseline_path), baseline)
    best_debug = []
    for index, frame in enumerate(after, start=1):
        image = decode(bytes(frame["jpg"]))
        score = _diff_score(_gray_roi(image, answer_box), baseline_roi)
        elapsed_ms = (float(frame["t"]) - started) * 1000
        best_debug.append({"elapsed_ms": round(elapsed_ms, 1), "mean": round(score[0], 3), "pixels": score[1]})
        if elapsed_ms >= 0 and (score[0] >= 3.0 or score[1] >= 7000):
            answer_path = case_dir / "visual_first_answer_frame.jpg"
            cv2.imwrite(str(answer_path), image)
            return {
                "status": "ok",
                "visual_first_response_time_ms": round(elapsed_ms, 1),
                "frame_count": len(frames),
                "baseline_frame": str(baseline_path),
                "first_answer_frame": str(answer_path),
                "answer_diff": {"mean": round(score[0], 3), "pixels": score[1]},
                "debug_first_frames": best_debug[:10],
            }
    return {
        "status": "not_detected",
        "reason": "threshold_not_reached",
        "frame_count": len(frames),
        "debug_first_frames": best_debug[:10],
    }


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
    def label(self) -> str:
        return self.text or self.desc or self.resource_id

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def adb_cmd(args: list[str]) -> list[str]:
    return ["adb", *(["-s", SERIAL] if SERIAL else []), *args]


def adb(args: list[str], timeout: int = 30, text: bool = True) -> str | bytes:
    result = subprocess.run(
        adb_cmd(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
    )
    if result.returncode != 0:
        stdout = result.stdout if text else result.stdout.decode("utf-8", "replace")
        stderr = result.stderr if text else result.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"{' '.join(adb_cmd(args))} failed\nstdout={stdout}\nstderr={stderr}")
    return result.stdout


def adb_no_raise(args: list[str], timeout: int = 30) -> str:
    try:
        return str(adb(args, timeout=timeout))
    except Exception as exc:
        return f"ERROR: {exc}"


def u2_device():
    return u2.connect_usb(SERIAL) if SERIAL else u2.connect_usb()


def parse_bounds(raw: str) -> tuple[int, int, int, int]:
    nums = [int(item) for item in re.findall(r"\d+", raw)]
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
    try:
        xml = u2_device().dump_hierarchy(compressed=False, pretty=True)
        if xml.strip():
            path.write_text(xml, encoding="utf-8")
            return parse_xml(path)
    except Exception:
        pass

    remote = "/sdcard/phone2app_window.xml"
    adb(["shell", "uiautomator", "dump", remote], timeout=25)
    adb(["pull", remote, str(path)], timeout=25)
    adb_no_raise(["shell", "rm", "-f", remote], timeout=10)
    return parse_xml(path)


def screencap(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = adb(["exec-out", "screencap", "-p"], timeout=20, text=False)
    path.write_bytes(bytes(data))


def tap_xy(x: int, y: int) -> None:
    adb(["shell", "input", "tap", str(x), str(y)], timeout=10)


def tap_node(node: Node) -> None:
    x, y = node.center
    tap_xy(x, y)


def swipe_left(y: int, duration_ms: int = 420) -> None:
    adb(["shell", "input", "swipe", "930", str(y), "130", str(y), str(duration_ms)], timeout=10)


def press_back() -> None:
    adb(["shell", "input", "keyevent", "BACK"], timeout=10)


def foreground_summary() -> str:
    text = adb_no_raise(["shell", "dumpsys", "window"], timeout=20)
    return "\n".join(
        line.strip()
        for line in text.splitlines()
        if "mCurrentFocus" in line or "mFocusedApp" in line
    )[:2000]


def launch(package: str) -> None:
    adb(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], timeout=30)
    time.sleep(1.5)


def force_stop(package: str) -> None:
    adb_no_raise(["shell", "am", "force-stop", package], timeout=15)
    time.sleep(0.8)


def page_labels(nodes: Iterable[Node], package: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if node.package and node.package != package:
            continue
        value = (node.text or node.desc).strip()
        if value and value not in seen:
            seen.add(value)
            labels.append(value)
    return labels


def find_by_id(nodes: Iterable[Node], suffix: str) -> Node | None:
    return next((node for node in nodes if node.resource_id.endswith(suffix)), None)


def find_text(nodes: Iterable[Node], text: str, package: str | None = None) -> Node | None:
    for node in nodes:
        if package and node.package and node.package != package:
            continue
        if text in node.text or text in node.desc:
            return node
    return None


def find_clickable_ancestor_or_self(nodes: list[Node], node: Node) -> Node:
    if node.clickable:
        return node
    left, top, right, bottom = node.bounds
    candidates = [
        item
        for item in nodes
        if item.clickable
        and item.bounds[0] <= left
        and item.bounds[1] <= top
        and item.bounds[2] >= right
        and item.bounds[3] >= bottom
    ]
    if candidates:
        return min(candidates, key=lambda item: (item.bounds[2] - item.bounds[0]) * (item.bounds[3] - item.bounds[1]))
    return node


def set_fast_input():
    device = u2_device()
    try:
        device.set_input_ime(True)
    except Exception:
        device.set_fastinput_ime(True)
    return device


def estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    ascii_runs = re.findall(r"[A-Za-z0-9_]+|[^\s\u3400-\u9fff\uf900-\ufaff]", text)
    ascii_tokens = sum(max(1, (len(run) + 3) // 4) for run in ascii_runs)
    return cjk + ascii_tokens


def is_noise(label: str) -> bool:
    noise = {
        "文本",
        "通话",
        "日报已阅",
        "日报待阅",
        "记忆管理",
        "会议助手",
        "智能绘画",
        "灵犀看看",
        "音视频通话",
        "AI创作",
        "语音播客",
        "快速",
        "拍题答疑",
        "帮我写作",
        "AI 创作",
        "内容由 AI 生成",
        "内容由豆包 AI 生成",
        "内容由AI生成",
        "思考",
        "Float Min",
        "关闭性格",
        "更多面板",
        "文本输入",
        "语音输入",
        "朗读已关闭",
        "深度思考，已关闭",
        "打电话",
        "返回",
        "新对话",
        "豆包",
        "灵犀",
        "Hi, 有什么需要我帮忙的？",
        "在此输入您的问题~",
        "发消息...",
        "点击说话",
        "按住说话",
        "已收到您的需求",
        "正在理解用户意图",
        "正在进行需求处理",
        "已完成数据检索",
        "正在进行数据汇总分析",
        "正在整理输出内容",
        PROMPT,
    }
    if not label or label in noise:
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", label):
        return True
    if label.startswith("新对话，"):
        return True
    return False


def answer_text(before: list[str], after: list[str]) -> str:
    before_counts: dict[str, int] = {}
    for label in before:
        before_counts[label] = before_counts.get(label, 0) + 1
    new_items: list[str] = []
    for label in after:
        value = label.strip()
        count = before_counts.get(value, 0)
        if count > 0:
            before_counts[value] = count - 1
            continue
        if is_noise(value):
            continue
        if value not in new_items:
            new_items.append(value)
    return "\n".join(new_items[-10:])[:4000]


def is_loading(nodes: list[Node], product: str) -> bool:
    labels = "\n".join(node.label for node in nodes)
    if product == "doubao":
        return any(node.resource_id.endswith(suffix) for node in nodes for suffix in (":id/v_dot1", ":id/v_dot2", ":id/v_dot3"))
    return any(
        token in labels
        for token in (
            "思考中",
            "正在生成",
            "加载中",
            "正在回答",
            "已收到您的需求",
            "正在理解用户意图",
            "正在进行需求处理",
            "已完成数据检索",
            "正在进行数据汇总分析",
            "正在整理输出内容",
        )
    )


def wait_for_stable_answer(
    product: str,
    package: str,
    case_dir: Path,
    before_labels: list[str],
    started: float,
    timeout_s: float,
) -> tuple[str, float | None, float, Path, Path, list[dict[str, object]]]:
    first_ms: float | None = None
    complete_ms: float | None = None
    last = ""
    best = ""
    stable = 0
    poll_log: list[dict[str, object]] = []
    last_png = case_dir / "response.png"
    last_xml = case_dir / "response.xml"
    while time.perf_counter() - started < timeout_s:
        prefix = f"poll_{len(poll_log) + 1:03d}"
        nodes = dump_xml(case_dir / f"{prefix}.xml")
        labels = page_labels(nodes, package)
        candidate = answer_text(before_labels, labels)
        loading = is_loading(nodes, product)
        elapsed_ms = (time.perf_counter() - started) * 1000
        last_xml = case_dir / f"{prefix}.xml"
        content_changed = bool(candidate and candidate != last)
        if candidate and first_ms is None:
            first_ms = elapsed_ms
        if candidate:
            best = candidate
        if content_changed:
            screencap(case_dir / f"{prefix}.png")
            last_png = case_dir / f"{prefix}.png"
        if candidate and candidate == last and not loading:
            stable += 1
            if stable == 1:
                screencap(case_dir / f"{prefix}.png")
                last_png = case_dir / f"{prefix}.png"
        else:
            stable = 0
            last = candidate
        poll_log.append(
            {
                "poll": len(poll_log) + 1,
                "elapsed_ms": round(elapsed_ms, 1),
                "loading": loading,
                "content_changed": content_changed,
                "candidate": candidate,
            }
        )
        if candidate and stable >= 2:
            complete_ms = elapsed_ms
            break
        time.sleep(0.12 if first_ms is None else 0.8)
    if complete_ms is None:
        complete_ms = (time.perf_counter() - started) * 1000
    return best or last, first_ms, complete_ms, last_png, last_xml, poll_log


def team_new_chat(case_dir: Path) -> list[Node]:
    force_stop(TEAM_PACKAGE)
    launch(TEAM_PACKAGE)
    nodes = dump_xml(case_dir / "team_start.xml")
    if "新建会话" in "\n".join(page_labels(nodes, TEAM_PACKAGE)) and "输入消息" not in "\n".join(page_labels(nodes, TEAM_PACKAGE)):
        tap_xy(950, 1000)
        time.sleep(0.7)
    tap_xy(70, 172)
    time.sleep(0.7)
    nodes = dump_xml(case_dir / "team_left_menu.xml")
    target = find_text(nodes, "新建会话", TEAM_PACKAGE)
    if target:
        tap_node(target)
    else:
        tap_xy(201, 347)
    time.sleep(1.0)
    nodes = dump_xml(case_dir / "team_new_chat.xml")
    if find_text(nodes, "点击说话", TEAM_PACKAGE) and not any(node.cls == "android.widget.EditText" for node in nodes):
        tap_xy(872, 2098)
        time.sleep(0.8)
        nodes = dump_xml(case_dir / "team_text_mode.xml")
    return nodes


def team_send_prompt(case_dir: Path, timeout_s: float) -> dict[str, object]:
    device = set_fast_input()
    nodes = team_new_chat(case_dir)
    before = page_labels(nodes, TEAM_PACKAGE)
    edit = next((node for node in nodes if node.cls == "android.widget.EditText"), None)
    if not edit:
        raise RuntimeError("团队版灵犀未找到文本输入框")
    tap_node(edit)
    time.sleep(0.2)
    device.send_keys(PROMPT, clear=True)
    typed_nodes = dump_xml(case_dir / "typed.xml")
    screencap(case_dir / "typed.png")
    edit = next((node for node in typed_nodes if node.cls == "android.widget.EditText"), edit)
    send_candidates = [
        node
        for node in typed_nodes
        if node.clickable
        and node.cls == "android.widget.ImageView"
        and node.bounds[0] >= edit.bounds[2] - 20
        and node.bounds[1] >= edit.bounds[1] - 80
        and node.bounds[3] >= edit.bounds[3] - 10
    ]
    send = max(send_candidates, key=lambda item: item.bounds[2]) if send_candidates else None
    if not send:
        send = find_text(typed_nodes, "发送", TEAM_PACKAGE)
    if not send:
        raise RuntimeError("团队版灵犀输入后未找到发送按钮")
    visual_capture = start_minicap_capture(case_dir, "team_first_2s", duration_s=2.0)
    tap_node(send)
    started = time.perf_counter()
    actual, first_ms, complete_ms, response_png, response_xml, poll_log = wait_for_stable_answer(
        "team", TEAM_PACKAGE, case_dir, before, started, timeout_s
    )
    stop_minicap_capture(visual_capture)
    result = build_result("团队版灵犀", "input_send", actual, first_ms, complete_ms, response_png, response_xml, poll_log)
    visual = analyze_team_minicap_visual(visual_capture, started, case_dir)
    result["visual_first_response"] = visual
    if visual.get("status") == "ok":
        result["visual_first_response_time_ms"] = visual.get("visual_first_response_time_ms")
    return result


def mobile_open_new_chat(case_dir: Path) -> list[Node]:
    sys.path.insert(0, str(Path("tools").resolve()))
    from mobile_lingxi_common import open_new_chat

    launch(MOBILE_PACKAGE)
    return open_new_chat(case_dir, "mobile_new_chat")


def doubao_open_new_chat(case_dir: Path) -> list[Node]:
    launch(DOUBAO_PACKAGE)
    nodes = dump_xml(case_dir / "doubao_before_new_chat.xml")
    create = find_by_id(nodes, ":id/side_bar_create_conversation")
    if not create:
        back = find_by_id(nodes, ":id/back_icon")
        if back:
            tap_node(back)
            time.sleep(0.8)
            nodes = dump_xml(case_dir / "doubao_sidebar.xml")
            create = find_by_id(nodes, ":id/side_bar_create_conversation")
    if create:
        tap_node(create)
        time.sleep(1.0)
        nodes = dump_xml(case_dir / "doubao_after_new_chat.xml")
    return nodes


def find_and_click_music_shortcut(
    product: str,
    package: str,
    case_dir: Path,
    nodes: list[Node],
    swipes: int,
) -> tuple[list[str], float]:
    for index in range(swipes + 1):
        screencap(case_dir / f"shortcut_search_{index:02d}.png")
        (case_dir / f"shortcut_search_{index:02d}.nodes.json").write_text(
            json.dumps([asdict(node) for node in nodes], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        target = find_text(nodes, PROMPT, package)
        if target:
            before = page_labels(nodes, package)
            clickable = find_clickable_ancestor_or_self(nodes, target)
            tap_node(clickable)
            started = time.perf_counter()
            return before, started
        y = 1845 if product == "mobile" else 1948
        if product == "doubao":
            y = 1948
        swipe_left(y)
        time.sleep(0.7)
        nodes = dump_xml(case_dir / f"shortcut_after_swipe_{index + 1:02d}.xml")
    raise RuntimeError(f"{product} 横滑 {swipes} 次后未找到“{PROMPT}”快捷标签")


def click_shortcut_case(product: str, package: str, case_dir: Path, timeout_s: float, swipes: int) -> dict[str, object]:
    if product == "mobile":
        nodes = mobile_open_new_chat(case_dir)
    elif product == "doubao":
        nodes = doubao_open_new_chat(case_dir)
    else:
        raise ValueError(product)
    before, started = find_and_click_music_shortcut(product, package, case_dir, nodes, swipes)
    actual, first_ms, complete_ms, response_png, response_xml, poll_log = wait_for_stable_answer(
        product, package, case_dir, before, started, timeout_s
    )
    name = "移动灵犀" if product == "mobile" else "豆包"
    return build_result(name, "shortcut_click", actual, first_ms, complete_ms, response_png, response_xml, poll_log)


def build_result(
    product_name: str,
    trigger: str,
    actual: str,
    first_ms: float | None,
    complete_ms: float,
    response_png: Path,
    response_xml: Path,
    poll_log: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "product": product_name,
        "trigger": trigger,
        "prompt": PROMPT,
        "actual": actual,
        "estimated_output_tokens": estimate_tokens(actual),
        "first_response_time_ms": round(first_ms, 1) if first_ms is not None else None,
        "response_complete_time_ms": round(complete_ms, 1),
        "response_screenshot": str(response_png),
        "response_xml": str(response_xml),
        "poll_count": len(poll_log),
        "poll_log": poll_log,
        "status": "ok" if actual.strip() else "no_response_captured",
    }


def write_report(run_dir: Path, results: list[dict[str, object]], metadata: dict[str, object]) -> None:
    payload = {"metadata": metadata, "results": results}
    (run_dir / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 来点音乐时延统计",
        "",
        f"- Run ID: `{metadata['run_id']}`",
        f"- 开始时间: `{metadata['start_time']}`",
        f"- 结束时间: `{metadata.get('end_time', '')}`",
        f"- 说明: token 为本地可见回答文本的估算值，非 App 服务端真实 token 账单。",
        "",
        "| App | 触发方式 | 状态 | 视觉first-token ms | XML first-token ms | 完全回答 ms | 输出token估算 | 回答摘要 | 截图 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for item in results:
        actual = str(item.get("actual", "")).replace("\n", " ")
        if len(actual) > 140:
            actual = actual[:139] + "..."
        actual = actual.replace("|", "\\|")
        lines.append(
            f"| {item.get('product')} | {item.get('trigger')} | {item.get('status')} | "
            f"{item.get('visual_first_response_time_ms') or ''} | "
            f"{item.get('first_response_time_ms') or ''} | {item.get('response_complete_time_ms') or ''} | "
            f"{item.get('estimated_output_tokens') or 0} | {actual} | {item.get('response_screenshot')} |"
        )
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="三款 App 的“来点音乐”触发到回答完成耗时统计")
    parser.add_argument("--products", default="team,mobile,doubao", help="逗号分隔：team,mobile,doubao")
    parser.add_argument("--timeout-s", type=float, default=45.0)
    parser.add_argument("--shortcut-swipes", type=int, default=8)
    parser.add_argument("--output-root", type=Path, default=Path("reports/music_shortcut_latency"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    selected = [part.strip() for part in args.products.split(",") if part.strip()]
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-music-shortcut")
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, object] = {
        "run_id": run_id,
        "start_time": now(),
        "products": selected,
        "timeout_s": args.timeout_s,
        "shortcut_swipes": args.shortcut_swipes,
        "device": adb_no_raise(["devices", "-l"], timeout=10).strip(),
        "foreground_start": foreground_summary(),
        "latency_definition": "first_response_time_ms 和 response_complete_time_ms 均从发送/点击动作返回后开始计时，不包含 adb tap 操作耗时；first 为首次观测到回答内容，complete 为回答内容连续稳定且无 loading 后的确认时间。",
    }
    results: list[dict[str, object]] = []
    tasks = {
        "team": lambda path: team_send_prompt(path, args.timeout_s),
        "mobile": lambda path: click_shortcut_case("mobile", MOBILE_PACKAGE, path, args.timeout_s, args.shortcut_swipes),
        "doubao": lambda path: click_shortcut_case("doubao", DOUBAO_PACKAGE, path, args.timeout_s, args.shortcut_swipes),
    }
    for product in selected:
        case_dir = run_dir / product
        case_dir.mkdir(parents=True, exist_ok=True)
        print(f"{now()} RUN {product}", flush=True)
        try:
            result = tasks[product](case_dir)
        except Exception as exc:
            err_png = case_dir / "error.png"
            err_xml = case_dir / "error.xml"
            try:
                screencap(err_png)
                dump_xml(err_xml)
            except Exception:
                pass
            result = {
                "product": product,
                "trigger": "input_send" if product == "team" else "shortcut_click",
                "prompt": PROMPT,
                "status": "error",
                "error": str(exc),
                "estimated_output_tokens": 0,
                "first_response_time_ms": None,
                "response_complete_time_ms": None,
                "response_screenshot": str(err_png),
                "response_xml": str(err_xml),
            }
        results.append(result)
        print(
            f"{now()} DONE {product} status={result.get('status')} "
            f"first_ms={result.get('first_response_time_ms')} complete_ms={result.get('response_complete_time_ms')} "
            f"tokens={result.get('estimated_output_tokens')}",
            flush=True,
        )
        write_report(run_dir, results, metadata)
    metadata["end_time"] = now()
    metadata["foreground_end"] = foreground_summary()
    write_report(run_dir, results, metadata)
    print(f"RESULT_DIR {run_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
