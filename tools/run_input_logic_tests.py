from __future__ import annotations

import json
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


PACKAGE = "com.chinamobile.eureka"
ACTIVITY = ".ui.main.MainActivity"


TESTS = [
    {
        "id": "H01_arithmetic_chain",
        "kind": "arithmetic",
        "prompt": "H01 Answer only final number Compute 18 times 7 minus 23",
        "expected": ["103"],
    },
    {
        "id": "H02_remainder",
        "kind": "arithmetic",
        "prompt": "H02 Answer only final number What is the remainder when 98765 is divided by 97",
        "expected": ["19"],
    },
    {
        "id": "H03_logic_boxes",
        "kind": "logic",
        "prompt": "H03 Answer only final color Gold is not in red Red label says gold is in blue Blue label says gold is not in blue Green label says gold is in red Exactly one label is true Which box has gold",
        "expected": ["blue"],
    },
    {
        "id": "H04_boolean_logic",
        "kind": "logic",
        "prompt": "H04 Answer only no or yes If A implies B and B implies not C and C is true Can A be true",
        "expected": ["no"],
    },
    {
        "id": "H05_average_speed",
        "kind": "math_word_problem",
        "prompt": "H05 Answer only final number A car goes 60 miles at 30 mph then 60 miles at 60 mph What is average speed in mph",
        "expected": ["40"],
    },
    {
        "id": "H06_sequence",
        "kind": "pattern",
        "prompt": "H06 Answer only final number Continue the sequence 2 6 12 20 30",
        "expected": ["42"],
    },
    {
        "id": "H07_grid_paths",
        "kind": "combinatorics",
        "prompt": "H07 Answer only final number From zero zero to three two moving only right or up how many shortest paths",
        "expected": ["10"],
    },
    {
        "id": "H08_set_logic",
        "kind": "set_reasoning",
        "prompt": "H08 Answer only final number Forty people like tea Thirty like coffee Ten like both Five like neither How many people total",
        "expected": ["65"],
    },
    {
        "id": "H09_calendar",
        "kind": "calendar_reasoning",
        "prompt": "H09 Answer only final weekday If today is Monday what weekday is 100 days later",
        "expected": ["Wednesday"],
    },
    {
        "id": "H10_family",
        "kind": "relation_reasoning",
        "prompt": "H10 Answer only final relation Ana is Ben mother Ben is Cara father What is Ana to Cara",
        "expected": ["grandmother", "grandma"],
    },
]


@dataclass
class Node:
    class_name: str
    text: str
    content_desc: str
    bounds: str
    clickable: bool

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        left_top, right_bottom = self.bounds.split("][")
        left, top = left_top.strip("[").split(",")
        right, bottom = right_bottom.strip("]").split(",")
        return int(left), int(top), int(right), int(bottom)

    @property
    def center(self) -> Tuple[int, int]:
        left, top, right, bottom = self.rect
        return (left + right) // 2, (top + bottom) // 2


def run(cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def dump_xml(output_dir: Path, name: str) -> Path:
    remote = f"/sdcard/phone2app-{name}.xml"
    local = output_dir / f"{name}.xml"
    run(f"adb shell uiautomator dump {remote}", timeout=30)
    pull = run(f'adb pull {remote} "{local}"', timeout=30)
    run(f"adb shell rm -f {remote}", timeout=10)
    if pull.returncode != 0 or not local.exists():
        raise RuntimeError(f"Failed to pull UI XML: {pull.stderr.strip()}")
    return local


def parse_nodes(xml_path: Path) -> List[Node]:
    root = ET.parse(xml_path).getroot()
    nodes: List[Node] = []
    for item in root.iter("node"):
        nodes.append(
            Node(
                class_name=item.attrib.get("class", ""),
                text=item.attrib.get("text", ""),
                content_desc=item.attrib.get("content-desc", ""),
                bounds=item.attrib.get("bounds", ""),
                clickable=item.attrib.get("clickable", "false") == "true",
            )
        )
    return nodes


def labels(nodes: Iterable[Node]) -> List[str]:
    out: List[str] = []
    for node in nodes:
        value = (node.text or node.content_desc).strip()
        if value:
            out.append(value)
    return out


def find_edit_text(nodes: Iterable[Node]) -> Node:
    edits = [node for node in nodes if node.class_name == "android.widget.EditText"]
    if not edits:
        raise LookupError("No EditText found on current screen.")
    return max(edits, key=lambda node: (node.rect[3], node.rect[2] - node.rect[0]))


def find_send_button(nodes: Iterable[Node], edit: Node) -> Node:
    edit_left, edit_top, edit_right, edit_bottom = edit.rect
    edit_mid_y = (edit_top + edit_bottom) // 2
    candidates: List[Node] = []
    for node in nodes:
        if not node.clickable or node.class_name != "android.widget.ImageView":
            continue
        left, top, right, bottom = node.rect
        mid_y = (top + bottom) // 2
        same_row = abs(mid_y - edit_mid_y) <= max(120, (edit_bottom - edit_top) * 2)
        right_of_input = left >= edit_right - 20
        if same_row and right_of_input:
            candidates.append(node)
    if not candidates:
        raise LookupError(f"No send button found near EditText bounds {edit.bounds}.")
    return max(candidates, key=lambda node: node.rect[2])


def tap(node: Node) -> None:
    x, y = node.center
    result = run(f"adb shell input tap {x} {y}", timeout=10)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


def type_ascii(text: str) -> None:
    escaped = text.replace(" ", "%s")
    result = run(f'adb shell input text "{escaped}"', timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


def clear_input_text(max_chars: int = 180) -> None:
    # One adb invocation with repeated DEL key events is much faster and more stable than
    # looping from Python. It also cleans up partial text left by interrupted runs.
    deletes = " ".join(["KEYCODE_DEL"] * max_chars)
    result = run(f"adb shell input keyevent KEYCODE_MOVE_END {deletes}", timeout=20)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())


def current_nodes(output_dir: Path, name: str) -> List[Node]:
    return parse_nodes(dump_xml(output_dir, name))


def score(all_text: str, expected: Iterable[str], reject: Optional[Iterable[str]] = None) -> bool:
    lower = all_text.lower()
    if reject and any(item.lower() in lower for item in reject):
        return False
    return any(item.lower() in lower for item in expected)


def response_labels(before: List[str], after: List[str], prompt: str) -> List[str]:
    new_items: List[str] = []
    for item in after:
        normalized = " ".join(item.split())
        if prompt in normalized or normalized == prompt:
            continue
        if item not in before and item not in new_items:
            new_items.append(item)
    return new_items


def response_excerpt(before: List[str], after: List[str], prompt: str) -> str:
    new_items = response_labels(before, after, prompt)
    source = new_items if new_items else [item for item in after[-8:] if prompt not in " ".join(item.split())]
    return "\n".join(source[-5:])[:1500]


def wait_for_response(
    output_dir: Path,
    name: str,
    before_labels: List[str],
    prompt: str,
    expected: Iterable[str],
    reject: Optional[Iterable[str]] = None,
    timeout_seconds: float = 13.0,
    interval_seconds: float = 1.0,
) -> Tuple[List[str], float, bool]:
    started = time.perf_counter()
    last_after: List[str] = before_labels
    last_response = ""
    stable_count = 0
    while True:
        elapsed = time.perf_counter() - started
        if elapsed > timeout_seconds:
            return last_after, elapsed * 1000, score(last_response, expected, reject)
        time.sleep(interval_seconds)
        nodes = current_nodes(output_dir, name)
        after = labels(nodes)
        candidate = response_excerpt(before_labels, after, prompt)
        if candidate and candidate == last_response:
            stable_count += 1
        else:
            stable_count = 0
        last_after = after
        last_response = candidate
        if candidate and score(candidate, expected, reject) and stable_count >= 1:
            return after, (time.perf_counter() - started) * 1000, True


def main() -> int:
    output_dir = Path("reports/input_tests") / datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    run(f"adb shell am start -W -n {PACKAGE}/{ACTIVITY}", timeout=30)
    time.sleep(2)

    results: List[Dict[str, object]] = []
    for index, case in enumerate(TESTS, start=1):
        before_nodes = current_nodes(output_dir, f"{index:02d}-{case['id']}-before")
        before_labels = labels(before_nodes)
        edit = find_edit_text(before_nodes)
        tap(edit)
        time.sleep(0.2)

        focused_nodes = current_nodes(output_dir, f"{index:02d}-{case['id']}-focused")
        edit = find_edit_text(focused_nodes)
        tap(edit)
        clear_input_text()
        type_ascii(str(case["prompt"]))
        time.sleep(0.2)

        typed_nodes = current_nodes(output_dir, f"{index:02d}-{case['id']}-typed")
        edit = find_edit_text(typed_nodes)
        send = find_send_button(typed_nodes, edit)
        tap(send)
        after_labels, elapsed_ms, passed = wait_for_response(
            output_dir=output_dir,
            name=f"{index:02d}-{case['id']}-after",
            before_labels=before_labels,
            prompt=str(case["prompt"]),
            expected=case["expected"],
            reject=case.get("reject"),
        )
        excerpt = response_excerpt(before_labels, after_labels, str(case["prompt"]))
        result = {
            **case,
            "passed": passed,
            "elapsed_ms": round(elapsed_ms, 1),
            "edit_bounds": edit.bounds,
            "send_bounds": send.bounds,
            "response_excerpt": excerpt,
        }
        results.append(result)
        print(f"{case['id']} passed={passed} elapsed_ms={elapsed_ms:.0f}")
        print(excerpt.replace("\n", " | ")[:400])
        print("---")
        time.sleep(1)

    summary = {
        "created_at": datetime.now().isoformat(),
        "app": f"{PACKAGE}/{ACTIVITY}",
        "device": run("adb devices -l", timeout=10).stdout.strip(),
        "pass_count": sum(1 for item in results if item["passed"]),
        "total": len(results),
        "results": results,
    }
    json_path = output_dir / "input_logic_results.json"
    md_path = output_dir / "input_logic_results.md"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(markdown(summary), encoding="utf-8")
    print(f"RESULT_DIR {output_dir}")
    print(f"PASS {summary['pass_count']}/{summary['total']}")
    return 0


def markdown(summary: Dict[str, object]) -> str:
    has_zh = any("zh_question" in dict(item) for item in summary["results"])  # type: ignore[index]
    lines = [
        "# Input Logic Test Results",
        "",
        f"- App: `{summary['app']}`",
        f"- Pass: `{summary['pass_count']}/{summary['total']}`",
        "",
    ]
    if has_zh:
        lines.extend(
            [
                "| ID | Kind | 中文题目 | Passed | Elapsed ms | Expected | Response excerpt |",
                "| --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
    else:
        lines.extend(
            [
                "| ID | Kind | Passed | Elapsed ms | Expected | Response excerpt |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
    for item in summary["results"]:  # type: ignore[index]
        row = dict(item)
        excerpt = str(row["response_excerpt"]).replace("\n", "<br>").replace("|", "\\|")[:500]
        expected = ", ".join(row["expected"])  # type: ignore[arg-type]
        if has_zh:
            zh = str(row.get("zh_question", "")).replace("|", "\\|")
            lines.append(
                f"| {row['id']} | {row['kind']} | {zh} | {row['passed']} | {row['elapsed_ms']} | {expected} | {excerpt} |"
            )
        else:
            lines.append(
                f"| {row['id']} | {row['kind']} | {row['passed']} | {row['elapsed_ms']} | {expected} | {excerpt} |"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
