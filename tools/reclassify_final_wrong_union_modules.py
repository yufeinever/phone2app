from __future__ import annotations

import html
import json
import shutil
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
SRC_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v6/final_wrong_union_overview.json")
SRC_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v6")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v7")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v7")

RECLASSIFY = {
    "MD-I03": "指令遵循",
    "MD-I07": "指令遵循",
    "MD-R11": "中文语言",
    "MD-Q01": "数学推理",
    "MD-C07": "代码能力",
    "MD-W03": "中文语言",
    "MD-W08": "指令遵循",
    "MD-T03": "事实常识",
    "MD-R07": "逻辑推理",
}

REPORT_RECLASSIFY = {
    cid: module
    for cid, module in RECLASSIFY.items()
    if cid != "MD-R07"
}

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


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def update_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = []
    for row in rows:
        item = dict(row)
        cid = item.get("case_id")
        if cid in RECLASSIFY:
            item["module"] = RECLASSIFY[cid]
            item["reclassified"] = True
        updated.append(item)
    order_index = {module: idx for idx, module in enumerate(MODULE_ORDER)}
    updated.sort(key=lambda row: (order_index.get(row.get("module", ""), 999), row.get("index", 9999), row.get("case_id", "")))
    for idx, row in enumerate(updated, start=1):
        row["index"] = idx
    return updated


def update_removed_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updated = []
    for row in rows:
        item = dict(row)
        cid = item.get("case_id")
        if cid in RECLASSIFY:
            item["module"] = RECLASSIFY[cid]
            item["reclassified"] = True
        updated.append(item)
    return updated


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


def product_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        product: sum(1 for row in rows if row.get("status", {}).get(product) == "错")
        for product in PRODUCTS
    }


def write_overview(src: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = product_counts(rows)
    stats = module_stats(rows)
    payload_src = dict(src)
    payload_src.pop("module_counts", None)
    payload_src["removed_rows"] = update_removed_rows(payload_src.get("removed_rows", []))
    payload = {
        **payload_src,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "counts": counts,
        "union_count": len(rows),
        "rows": rows,
        "module_counts": stats,
        "reclassification": REPORT_RECLASSIFY,
        "removed_generic_modules": True,
    }
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 三产品最终不通过项并集概览 v7",
        "",
        "- 已移除泛化基础能力模块，其 8 个用例已迁移到更具体模块。",
        f"- 并集总行数：`{len(rows)}`",
        "",
        "| 产品 | 最终不通过数 |",
        "| --- | ---: |",
    ]
    for product in PRODUCTS:
        lines.append(f"| {product} | {counts[product]} |")
    lines.extend(["", "## 模块统计", "", "| 模块 | 并集题数 | 团队版灵犀错 | 移动灵犀错 | 豆包错 |", "| --- | ---: | ---: | ---: | ---: |"])
    for module, stat in stats.items():
        lines.append(f"| {module} | {stat['union']} | {stat['团队版灵犀']} | {stat['移动灵犀']} | {stat['豆包']} |")
    lines.extend(["", "## 迁移明细", "", "| 用例 | 新模块 |", "| --- | --- |"])
    for cid, module in REPORT_RECLASSIFY.items():
        lines.append(f"| {cid} | {module} |")
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def extract_case_sections(html_text: str) -> dict[str, str]:
    import re

    sections = {}
    for match in re.finditer(r'(<section class="case-card" id="case-([^"]+)">.*?</section>)', html_text, re.S):
        sections[match.group(2)] = match.group(1)
    return sections


def remove_old_main(html_text: str) -> str:
    import re

    main_start = html_text.index("<main>")
    main_end = html_text.index("</main>")
    return html_text[: main_start + len("<main>")] + "__MAIN_PLACEHOLDER__" + html_text[main_end:]


def overview_html(payload: dict[str, Any]) -> str:
    stats = payload["module_counts"]
    counts = payload["counts"]
    rows = [
        '<div class="overview"><table><thead><tr><th>产品</th><th>最终不通过数</th></tr></thead><tbody>',
    ]
    for product in PRODUCTS:
        rows.append(f"<tr><td>{esc(product)}</td><td>{counts[product]}</td></tr>")
    rows.append(f"<tr><td>并集总行数</td><td>{payload['union_count']}</td></tr></tbody></table><br>")
    rows.append("<table><thead><tr><th>模块</th><th>并集题数</th><th>灵犀错</th><th>移动错</th><th>豆包错</th></tr></thead><tbody>")
    for module, stat in stats.items():
        rows.append(
            f"<tr><td>{esc(module)}</td><td>{stat['union']}</td><td>{stat['团队版灵犀']}</td><td>{stat['移动灵犀']}</td><td>{stat['豆包']}</td></tr>"
        )
    rows.append("</tbody></table></div>")
    return "".join(rows)


def nav_html(rows: list[dict[str, Any]], stats: OrderedDict[str, dict[str, int]]) -> str:
    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict((module, []) for module in stats)
    for row in rows:
        grouped.setdefault(row.get("module", ""), []).append(row)
    parts = ['<div class="nav-title">导航</div><div class="nav-note">红色表示该产品错；蓝色表示非错。泛化基础能力模块已迁移到具体能力标签。</div>']
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


def main_content(rows: list[dict[str, Any]], sections: dict[str, str], payload: dict[str, Any]) -> str:
    import re

    grouped: OrderedDict[str, list[dict[str, Any]]] = OrderedDict((module, []) for module in payload["module_counts"])
    for row in rows:
        grouped.setdefault(row.get("module", ""), []).append(row)
    parts = [overview_html(payload)]
    for module, items in grouped.items():
        parts.append(f'<h2 class="module-heading" id="module-{esc(module)}">{esc(module)} <span>{len(items)} 题</span></h2>')
        for row in items:
            section = sections.get(row["case_id"], "")
            section = re.sub(
                r'<div class="case-no">#\d+</div>',
                f'<div class="case-no">#{row["index"]}</div>',
                section,
                count=1,
            )
            # Replace the old module heading is unnecessary; section itself only shows feature.
            parts.append(section)
    return "".join(parts)


def update_html(payload: dict[str, Any]) -> None:
    if OUT_HTML_DIR.exists():
        shutil.rmtree(OUT_HTML_DIR)
    shutil.copytree(SRC_HTML_DIR, OUT_HTML_DIR)
    html_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review.html"
    text = html_path.read_text(encoding="utf-8")
    text = text.replace("三产品最终不通过项并集横向复核 v6", "三产品最终不通过项并集横向复核 v7")
    text = text.replace("phone2app.finalWrongUnion.v6.reviewDecisions", "phone2app.finalWrongUnion.v7.reviewDecisions")
    text = text.replace("已应用人工提交：MD-R07、MD-X04、MD-X08、MD-X11、MD-X20 转不计分/需换题。 ", "已应用人工提交并重整模块。 ")
    sections = extract_case_sections(text)
    base = remove_old_main(text)
    rows = payload["rows"]
    stats = payload["module_counts"]
    # Replace aside content.
    base = base.replace(base[base.index("<aside>") + len("<aside>") : base.index("</aside>")], nav_html(rows, stats), 1)
    text = base.replace("__MAIN_PLACEHOLDER__", main_content(rows, sections, payload))
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
            "reclassification": REPORT_RECLASSIFY,
            "removed_generic_modules": True,
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT_OVERVIEW_DIR / "final_wrong_union_overview.md", OUT_HTML_DIR / "final_wrong_union_horizontal_review.md")


def main() -> int:
    src = load_json(SRC_OVERVIEW)
    rows = update_rows(src["rows"])
    payload = write_overview(src, rows)
    update_html(payload)
    print(f"HTML {OUT_HTML_DIR / 'final_wrong_union_horizontal_review.html'}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print("RECLASSIFIED", json.dumps(REPORT_RECLASSIFY, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
