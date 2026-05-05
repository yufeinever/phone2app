from __future__ import annotations

import html
import json
import re
import shutil
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
SRC_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v7/final_wrong_union_overview.json")
SRC_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v7")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v8")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v8")

MODULE_ORDER = [
    "主对话-模型能力",
    "逻辑推理",
    "学科考察",
    "指令遵循",
    "数学推理",
    "代码能力",
    "中文语言",
    "上下文多轮",
    "事实常识",
    "安全红队",
]

SUBMISSION = {
    "created_at": "2026-05-05T11:06:40.542Z",
    "source_html": "file:///D:/phone2app/reports/compare_eval/final-wrong-union-horizontal-review-20260505-v7/final_wrong_union_horizontal_review.html#case-MD-EX-C05",
    "storage_key": "phone2app.finalWrongUnion.v7.reviewDecisions",
    "product_order": PRODUCTS,
    "decisions": [
        {"case_id": "MD-EX-C08", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:15.278Z"},
        {"case_id": "MD-EX-C08", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:16.387Z"},
        {"case_id": "MD-EX-C08", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:17.795Z"},
        {"case_id": "MD-EX-C15", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:32.034Z"},
        {"case_id": "MD-EX-C15", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:33.311Z"},
        {"case_id": "MD-EX-C15", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T11:06:34.833Z"},
    ],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def fully_unscorable_case_ids() -> set[str]:
    grouped: dict[str, dict[str, str]] = {}
    for item in SUBMISSION["decisions"]:
        grouped.setdefault(item["case_id"], {})[item["product"]] = item["action"]
    return {
        case_id
        for case_id, actions in grouped.items()
        if all(actions.get(product) == "unscorable" for product in PRODUCTS)
    }


def product_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        product: sum(1 for row in rows if row.get("status", {}).get(product) == "错")
        for product in PRODUCTS
    }


def module_stats(rows: list[dict[str, Any]]) -> OrderedDict[str, dict[str, int]]:
    stats: OrderedDict[str, dict[str, int]] = OrderedDict()
    for module in MODULE_ORDER:
        stats[module] = {"union": 0, **{product: 0 for product in PRODUCTS}}
    for row in rows:
        module = row.get("module", "")
        stats.setdefault(module, {"union": 0, **{product: 0 for product in PRODUCTS}})
        stats[module]["union"] += 1
        for product in PRODUCTS:
            if row.get("status", {}).get(product) == "错":
                stats[module][product] += 1
    return OrderedDict((module, stat) for module, stat in stats.items() if stat["union"] > 0)


def build_payload() -> dict[str, Any]:
    src = load_json(SRC_OVERVIEW)
    remove_ids = fully_unscorable_case_ids()
    removed = [row for row in src["rows"] if row.get("case_id") in remove_ids]
    rows = [dict(row) for row in src["rows"] if row.get("case_id") not in remove_ids]
    for idx, row in enumerate(rows, start=1):
        row["index"] = idx
    removed_rows = list(src.get("removed_rows", [])) + removed
    counts = product_counts(rows)
    stats = module_stats(rows)
    payload_src = dict(src)
    payload_src.pop("module_counts", None)
    return {
        **payload_src,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "union_count": len(rows),
        "rows": rows,
        "applied_review_submission": SUBMISSION,
        "latest_review_submission": SUBMISSION,
        "removed_as_unscorable_case_ids": sorted(set(src.get("removed_as_unscorable_case_ids", [])) | remove_ids),
        "latest_removed_as_unscorable_case_ids": sorted(remove_ids),
        "removed_rows": removed_rows,
        "module_counts": stats,
    }


def write_overview(payload: dict[str, Any]) -> None:
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_OVERVIEW_DIR / "review_submission.json").write_text(
        json.dumps(SUBMISSION, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 三产品最终不通过项并集概览 v8",
        "",
        "- 已应用人工提交：`MD-EX-C08`、`MD-EX-C15` 三家均转为不计分/需换题。",
        f"- 并集总行数：`{payload['union_count']}`",
        "",
        "| 产品 | 最终不通过数 |",
        "| --- | ---: |",
    ]
    for product in PRODUCTS:
        lines.append(f"| {product} | {payload['counts'][product]} |")
    lines.extend(["", "## 模块统计", "", "| 模块 | 并集题数 | 团队版灵犀错 | 移动灵犀错 | 豆包错 |", "| --- | ---: | ---: | ---: | ---: |"])
    for module, stat in payload["module_counts"].items():
        lines.append(f"| {module} | {stat['union']} | {stat['团队版灵犀']} | {stat['移动灵犀']} | {stat['豆包']} |")
    lines.extend(["", "## 本次转不计分/需换题", "", "| 用例 | 模块 | 原状态 |", "| --- | --- | --- |"])
    for row in payload["removed_rows"]:
        if row.get("case_id") in payload["latest_removed_as_unscorable_case_ids"]:
            status = "；".join(f"{p}:{row.get('status', {}).get(p)}" for p in PRODUCTS)
            lines.append(f"| {row.get('case_id')} | {row.get('module')} | {status} |")
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def extract_case_sections(html_text: str) -> dict[str, str]:
    return {
        match.group(2): match.group(1)
        for match in re.finditer(r'(<section class="case-card" id="case-([^"]+)">.*?</section>)', html_text, re.S)
    }


def overview_html(payload: dict[str, Any]) -> str:
    parts = ['<div class="overview"><table><thead><tr><th>产品</th><th>最终不通过数</th></tr></thead><tbody>']
    for product in PRODUCTS:
        parts.append(f"<tr><td>{esc(product)}</td><td>{payload['counts'][product]}</td></tr>")
    parts.append(f"<tr><td>并集总行数</td><td>{payload['union_count']}</td></tr></tbody></table><br>")
    parts.append("<table><thead><tr><th>模块</th><th>并集题数</th><th>灵犀错</th><th>移动错</th><th>豆包错</th></tr></thead><tbody>")
    for module, stat in payload["module_counts"].items():
        parts.append(f"<tr><td>{esc(module)}</td><td>{stat['union']}</td><td>{stat['团队版灵犀']}</td><td>{stat['移动灵犀']}</td><td>{stat['豆包']}</td></tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def nav_html(rows: list[dict[str, Any]], stats: OrderedDict[str, dict[str, int]]) -> str:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict((module, []) for module in stats)
    for row in rows:
        grouped.setdefault(row.get("module", ""), []).append(row)
    parts = ['<div class="nav-title">导航</div><div class="nav-note">红色表示该产品错；蓝色表示非错。本版已移除 MD-EX-C08、MD-EX-C15。</div>']
    for module, items in grouped.items():
        parts.append(f'<div class="nav-module"><a class="module-link" href="#module-{esc(module)}">{esc(module)} <span>{len(items)}</span></a><div class="nav-cases">')
        for row in items:
            chips = []
            for product, short in [("团队版灵犀", "灵犀"), ("移动灵犀", "移动"), ("豆包", "豆包")]:
                bad = row.get("status", {}).get(product) == "错"
                chips.append(f'<span class="mini {"bad" if bad else "ok"}">{short}</span>')
            parts.append(f'<a href="#case-{esc(row["case_id"])}"><b>{esc(row["case_id"])}</b> {"".join(chips)}</a>')
        parts.append("</div></div>")
    return "".join(parts)


def main_content(payload: dict[str, Any], sections: dict[str, str]) -> str:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict((module, []) for module in payload["module_counts"])
    for row in payload["rows"]:
        grouped.setdefault(row.get("module", ""), []).append(row)
    parts = [overview_html(payload)]
    for module, items in grouped.items():
        parts.append(f'<h2 class="module-heading" id="module-{esc(module)}">{esc(module)} <span>{len(items)} 题</span></h2>')
        for row in items:
            section = sections.get(row["case_id"], "")
            section = re.sub(r'<div class="case-no">#\d+</div>', f'<div class="case-no">#{row["index"]}</div>', section, count=1)
            parts.append(section)
    return "".join(parts)


def update_html(payload: dict[str, Any]) -> None:
    if OUT_HTML_DIR.exists():
        shutil.rmtree(OUT_HTML_DIR)
    shutil.copytree(SRC_HTML_DIR, OUT_HTML_DIR)
    html_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review.html"
    text = html_path.read_text(encoding="utf-8")
    text = text.replace("三产品最终不通过项并集横向复核 v7", "三产品最终不通过项并集横向复核 v8")
    text = text.replace("phone2app.finalWrongUnion.v7.reviewDecisions", "phone2app.finalWrongUnion.v8.reviewDecisions")
    text = re.sub(
        r'<div class="summary">.*?</div></header>',
        f'<div class="summary">已应用人工提交：MD-EX-C08、MD-EX-C15 转不计分/需换题。共 <b>{payload["union_count"]}</b> 行，每行至少一家产品最终不通过。列顺序固定为：团队版灵犀、移动灵犀、豆包。</div></header>',
        text,
        count=1,
        flags=re.S,
    )
    sections = extract_case_sections(text)
    main_start = text.index("<main>")
    main_end = text.index("</main>")
    base = text[: main_start + len("<main>")] + "__MAIN_PLACEHOLDER__" + text[main_end:]
    aside_start = base.index("<aside>") + len("<aside>")
    aside_end = base.index("</aside>")
    base = base[:aside_start] + nav_html(payload["rows"], payload["module_counts"]) + base[aside_end:]
    text = base.replace("__MAIN_PLACEHOLDER__", main_content(payload, sections))
    html_path.write_text(text, encoding="utf-8")

    manifest_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review_manifest.json"
    manifest = load_json(manifest_path)
    manifest.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str((OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").resolve()),
            "union_count": payload["union_count"],
            "counts": payload["counts"],
            "module_counts": payload["module_counts"],
            "latest_review_submission": SUBMISSION,
            "latest_removed_as_unscorable_case_ids": payload["latest_removed_as_unscorable_case_ids"],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT_OVERVIEW_DIR / "final_wrong_union_overview.md", OUT_HTML_DIR / "final_wrong_union_horizontal_review.md")


def main() -> int:
    payload = build_payload()
    write_overview(payload)
    update_html(payload)
    print(f"HTML {OUT_HTML_DIR / 'final_wrong_union_horizontal_review.html'}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print(f"REMOVED {','.join(payload['latest_removed_as_unscorable_case_ids'])}")
    print(f"UNION {payload['union_count']}")
    print(f"COUNTS {json.dumps(payload['counts'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
