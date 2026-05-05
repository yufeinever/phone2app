from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import subprocess
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb


DATASET = "ceval/ceval-exam"
TREE_URLS = [
    f"https://huggingface.co/api/datasets/{DATASET}/tree/main?recursive=1",
    f"https://hf-mirror.com/api/datasets/{DATASET}/tree/main?recursive=1",
]
FILE_URLS = [
    "https://huggingface.co/datasets/{dataset}/resolve/main/{path}",
    "https://hf-mirror.com/datasets/{dataset}/resolve/main/{path}",
]
DEFAULT_OUT_DIR = Path("reports/product_eval/ceval-abcd-50-20260505")
DEFAULT_RAW_DIR = Path("data/ceval_abcd_50/raw")

BAD_PATTERNS = [
    "下图",
    "如图",
    "图中",
    "图片",
    "见图",
    "表中",
    "下表",
    "如表",
    "阅读材料",
    "材料一",
    "材料二",
    "根据材料",
]

SUBJECT_META: dict[str, tuple[str, str]] = {
    "logic": ("逻辑与公务员", "逻辑学"),
    "civil_servant": ("逻辑与公务员", "公务员"),
    "law": ("法律与公共知识", "法律"),
    "legal_professional": ("法律与公共知识", "法律职业资格"),
    "ideological_and_moral_cultivation": ("法律与公共知识", "思想道德修养"),
    "marxism": ("法律与公共知识", "马克思主义"),
    "high_school_politics": ("法律与公共知识", "高中政治"),
    "college_economics": ("法律与公共知识", "大学经济学"),
    "business_administration": ("法律与公共知识", "工商管理"),
    "accountant": ("法律与公共知识", "会计"),
    "chinese_language_and_literature": ("语言与人文", "中国语言文学"),
    "high_school_chinese": ("语言与人文", "高中语文"),
    "modern_chinese_history": ("历史地理", "近代史纲要"),
    "high_school_history": ("历史地理", "高中历史"),
    "middle_school_history": ("历史地理", "初中历史"),
    "high_school_geography": ("历史地理", "高中地理"),
    "middle_school_geography": ("历史地理", "初中地理"),
    "advanced_mathematics": ("数学", "高等数学"),
    "discrete_mathematics": ("数学", "离散数学"),
    "probability_and_statistics": ("数学", "概率统计"),
    "high_school_mathematics": ("数学", "高中数学"),
    "middle_school_mathematics": ("数学", "初中数学"),
    "college_physics": ("理科", "大学物理"),
    "high_school_physics": ("理科", "高中物理"),
    "middle_school_physics": ("理科", "初中物理"),
    "college_chemistry": ("理科", "大学化学"),
    "high_school_chemistry": ("理科", "高中化学"),
    "middle_school_chemistry": ("理科", "初中化学"),
    "computer_network": ("计算机", "计算机网络"),
    "computer_architecture": ("计算机", "计算机组成"),
    "operating_system": ("计算机", "操作系统"),
}

TARGET_BY_CATEGORY = {
    "逻辑与公务员": 10,
    "法律与公共知识": 8,
    "语言与人文": 5,
    "历史地理": 7,
    "数学": 8,
    "理科": 8,
    "计算机": 4,
}


def fetch_json(urls: list[str], timeout_s: int) -> Any:
    errors: list[str] = []
    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$ProgressPreference='SilentlyContinue'; "
                        f"(Invoke-WebRequest -Uri '{url}' -TimeoutSec {timeout_s} -UseBasicParsing).Content"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s + 10,
            )
            return json.loads(completed.stdout)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url} via PowerShell: {type(exc).__name__}: {exc}")
    raise RuntimeError("fetch_json failed:\n" + "\n".join(errors))


def download_file(path: str, out_path: Path, timeout_s: int, force: bool = False) -> None:
    if out_path.exists() and out_path.stat().st_size > 0 and not force:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for template in FILE_URLS:
        url = template.format(dataset=DATASET, path=path)
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as response:
                content = response.read()
            if len(content) < 128:
                raise RuntimeError(f"downloaded content too small: {len(content)} bytes")
            out_path.write_bytes(content)
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
            time.sleep(0.5)
        try:
            completed = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "$ProgressPreference='SilentlyContinue'; "
                        f"Invoke-WebRequest -Uri '{url}' -OutFile '{out_path}' -TimeoutSec {timeout_s} -UseBasicParsing"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s + 10,
            )
            if out_path.exists() and out_path.stat().st_size >= 128:
                return
            errors.append(f"{url} via PowerShell: downloaded file too small")
        except Exception as exc:  # noqa: BLE001
            stderr = getattr(exc, "stderr", "") or ""
            errors.append(f"{url} via PowerShell: {type(exc).__name__}: {exc} {stderr.strip()}")
            time.sleep(0.5)
    raise RuntimeError("download_file failed for " + path + "\n" + "\n".join(errors))


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def prompt_for(row: dict[str, Any]) -> str:
    question = compact_text(row["question"]).replace("____", "")
    return "\n".join(
        [
            "以下是单项选择题。请仅回答选项 A、B、C、D 中的一个字母，不要解释，否则判定不通过。",
            f"科目：{row['subject_name']}",
            f"题目：{question}",
            f"A. {compact_text(row['A'])}",
            f"B. {compact_text(row['B'])}",
            f"C. {compact_text(row['C'])}",
            f"D. {compact_text(row['D'])}",
            "答案：",
        ]
    )


def is_good_row(row: dict[str, Any], max_prompt_chars: int) -> bool:
    if row["answer"] not in {"A", "B", "C", "D"}:
        return False
    fields = [row.get("question"), row.get("A"), row.get("B"), row.get("C"), row.get("D")]
    if any(not compact_text(field) for field in fields):
        return False
    full = "\n".join(compact_text(field) for field in fields)
    if any(token in full for token in BAD_PATTERNS):
        return False
    if len(prompt_for(row)) > max_prompt_chars:
        return False
    return True


def load_rows(raw_files: dict[str, Path], max_prompt_chars: int) -> list[dict[str, Any]]:
    con = duckdb.connect()
    rows: list[dict[str, Any]] = []
    for subject, path in sorted(raw_files.items()):
        category, subject_name = SUBJECT_META.get(subject, ("其他", subject))
        records = con.execute(
            "SELECT id, question, A, B, C, D, answer, explanation FROM read_parquet(?)",
            [str(path)],
        ).fetchall()
        for record in records:
            row = {
                "source_id": int(record[0]),
                "question": compact_text(record[1]),
                "A": compact_text(record[2]),
                "B": compact_text(record[3]),
                "C": compact_text(record[4]),
                "D": compact_text(record[5]),
                "answer": compact_text(record[6]).upper(),
                "explanation": compact_text(record[7]),
                "subject": subject,
                "subject_name": subject_name,
                "category": category,
            }
            if is_good_row(row, max_prompt_chars=max_prompt_chars):
                rows.append(row)
    return rows


def stable_key(row: dict[str, Any], seed: int) -> str:
    digest = hashlib.sha256(
        f"{seed}|{row['subject']}|{row['source_id']}|{row['question']}".encode("utf-8")
    ).hexdigest()
    return digest


def choose_rows(rows: list[dict[str, Any]], total: int, seed: int) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for category, target in TARGET_BY_CATEGORY.items():
        candidates = sorted(by_category.get(category, []), key=lambda row: stable_key(row, seed))
        # Spread each category across subjects before taking more from the same subject.
        by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in candidates:
            by_subject[row["subject"]].append(row)
        subject_order = sorted(by_subject, key=lambda subject: hashlib.sha256(f"{seed}|{category}|{subject}".encode()).hexdigest())
        while len([row for row in selected if row["category"] == category]) < target:
            advanced = False
            for subject in subject_order:
                bucket = by_subject[subject]
                if not bucket:
                    continue
                row = bucket.pop(0)
                key = (row["subject"], row["source_id"])
                if key in seen:
                    continue
                selected.append(row)
                seen.add(key)
                advanced = True
                if len([item for item in selected if item["category"] == category]) >= target:
                    break
            if not advanced:
                break
    if len(selected) < total:
        remaining = [
            row
            for row in sorted(rows, key=lambda item: stable_key(item, seed + 17))
            if (row["subject"], row["source_id"]) not in seen
        ]
        selected.extend(remaining[: total - len(selected)])
    rng = random.Random(seed)
    rng.shuffle(selected)
    return selected[:total]


def case_from_row(index: int, row: dict[str, Any]) -> dict[str, Any]:
    case_id = f"CEVAL-ABCD-{index:03d}"
    prompt = prompt_for(row)
    summary = compact_text(row["question"]).replace("____", "")[:80]
    return {
        "case_id": case_id,
        "priority": "P0",
        "module": "主对话-标准选择题",
        "feature": row["category"],
        "ability": row["subject_name"],
        "source": "C-Eval validation",
        "benchmark": "C-Eval",
        "benchmark_dataset": DATASET,
        "benchmark_split": "validation",
        "benchmark_subject": row["subject"],
        "benchmark_subject_name": row["subject_name"],
        "benchmark_source_id": row["source_id"],
        "source_fidelity": "原题引用",
        "source_fidelity_reason": "来自 C-Eval validation split 的原始单项选择题，保留原题题干、选项与标准答案。",
        "easy_wrong": "否",
        "summary": summary,
        "input": prompt,
        "expected_result": row["answer"],
        "steps": ["新建会话", "输入 C-Eval 单项选择题", "发送", "等待回答", "提取首个独立 A/B/C/D 判分并记录截图/XML/时延"],
        "recovery_action": "用新建会话隔离用例；必要时关闭当前 App 后拉起下一产品。",
        "test_type": "model_dialogue",
        "execution_mode": "uiautomator2_text_dialogue",
        "send_as_model_question": True,
        "execution_protocol": "text_dialogue_or_metric",
        "current_dialogue_suitable": "是",
        "needs_material": "否",
        "needs_operation": "否",
        "scoring_type": "single_choice_abcd",
        "strict_expected": row["answer"],
        "score_rule": "App 必须仅回答选项 A/B/C/D 中的一个字母，不要解释；与 strict_expected 完全一致为 correct，否则 wrong；不使用 partial。",
        "turns": [
            {
                "input": prompt,
                "expected": row["answer"],
                "must_contain": [row["answer"]],
                "scoring_type": "single_choice_abcd",
                "strict_answer_only": True,
            }
        ],
        "question": row["question"],
        "options": {"A": row["A"], "B": row["B"], "C": row["C"], "D": row["D"]},
        "answer": row["answer"],
        "explanation": row["explanation"],
    }


def md_cell(value: Any, limit: int = 180) -> str:
    text = str(value or "").replace("\n", " ").replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def write_reports(out_dir: Path, cases: list[dict[str, Any]], raw_paths: dict[str, str], seed: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "name": "ceval-abcd-50",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": DATASET,
        "split": "validation",
        "seed": seed,
        "case_count": len(cases),
        "raw_paths": raw_paths,
        "selection_rule": "C-Eval validation 单项选择题；过滤图表/材料风险题；prompt 长度受控；按能力域分层确定性抽样。",
        "product_order": ["团队版灵犀", "移动灵犀", "豆包"],
    }
    payload = {"metadata": metadata, "results": cases}
    (out_dir / "cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "dialogue_cases.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = [
        [
            "用例ID",
            "能力域",
            "科目",
            "C-Eval原ID",
            "题目摘要",
            "标准答案",
            "App回答",
            "结果",
            "截图/日志",
        ]
    ]
    for case in cases:
        rows.append(
            [
                case["case_id"],
                case["feature"],
                case["ability"],
                str(case["benchmark_source_id"]),
                md_cell(case["summary"], 90),
                case["strict_expected"],
                "",
                "待执行",
                "",
            ]
        )
    lines = [
        "# C-Eval A/B/C/D 标准选择题 50 题",
        "",
        f"- 数据源：`{DATASET}` validation split",
        "- 判分：必须仅回答选项 `A/B/C/D` 中的一个字母，不要解释；完全一致才算通过，不使用 partial。",
        "- 发送给 App 的 prompt 不包含测试编号；编号只用于报告和复跑。",
        "",
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * len(rows[0])) + " |",
    ]
    for row in rows[1:]:
        lines.append("| " + " | ".join(row) + " |")
    (out_dir / "case_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    category_counter = Counter(case["feature"] for case in cases)
    subject_counter = Counter((case["feature"], case["ability"]) for case in cases)
    dist_lines = [
        "# C-Eval A/B/C/D 50 题分布",
        "",
        "## 一级能力域",
        "",
        "| 能力域 | 题数 |",
        "| --- | ---: |",
    ]
    for category, count in sorted(category_counter.items()):
        dist_lines.append(f"| {category} | {count} |")
    dist_lines.extend(["", "## 二级科目", "", "| 能力域 | 科目 | 题数 |", "| --- | --- | ---: |"])
    for (category, subject), count in sorted(subject_counter.items()):
        dist_lines.append(f"| {category} | {subject} | {count} |")
    (out_dir / "subject_distribution.md").write_text("\n".join(dist_lines) + "\n", encoding="utf-8")

    csv_path = out_dir / "cases.csv"
    try:
        fh = csv_path.open("w", newline="", encoding="utf-8-sig")
    except PermissionError:
        csv_path = out_dir / f"cases-{datetime.now().strftime('%H%M%S')}.csv"
        fh = csv_path.open("w", newline="", encoding="utf-8-sig")
    with fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "case_id",
                "category",
                "subject",
                "source_id",
                "question",
                "A",
                "B",
                "C",
                "D",
                "answer",
            ],
        )
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "category": case["feature"],
                    "subject": case["ability"],
                    "source_id": case["benchmark_source_id"],
                    "question": case["question"],
                    "A": case["options"]["A"],
                    "B": case["options"]["B"],
                    "C": case["options"]["C"],
                    "D": case["options"]["D"],
                    "answer": case["answer"],
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 C-Eval A/B/C/D 标准选择题 50 题用例集")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--seed", type=int, default=20260505)
    parser.add_argument("--total", type=int, default=50)
    parser.add_argument("--timeout-s", type=int, default=45)
    parser.add_argument("--max-prompt-chars", type=int, default=700)
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()

    tree = fetch_json(TREE_URLS, timeout_s=args.timeout_s)
    val_entries = [
        item
        for item in tree
        if item.get("type") == "file"
        and item.get("path", "").endswith("val-00000-of-00001.parquet")
        and item.get("path", "").split("/", 1)[0] in SUBJECT_META
    ]
    if not val_entries:
        raise SystemExit("未找到 C-Eval validation parquet 文件")

    raw_files: dict[str, Path] = {}
    for entry in sorted(val_entries, key=lambda item: item["path"]):
        path = entry["path"]
        subject = path.split("/", 1)[0]
        out_path = args.raw_dir / subject / Path(path).name
        download_file(path, out_path, timeout_s=args.timeout_s, force=args.force_download)
        raw_files[subject] = out_path

    rows = load_rows(raw_files, max_prompt_chars=args.max_prompt_chars)
    selected = choose_rows(rows, total=args.total, seed=args.seed)
    if len(selected) < args.total:
        raise SystemExit(f"可用题数不足：{len(selected)}/{args.total}")
    cases = [case_from_row(index, row) for index, row in enumerate(selected, start=1)]
    raw_paths = {subject: str(path) for subject, path in sorted(raw_files.items())}
    write_reports(args.out_dir, cases, raw_paths=raw_paths, seed=args.seed)
    print(f"OUT_DIR {args.out_dir}")
    print(f"CASES {len(cases)}")
    print(f"CASE_SOURCE {args.out_dir / 'dialogue_cases.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
