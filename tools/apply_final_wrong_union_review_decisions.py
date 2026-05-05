from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
SRC_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v5/final_wrong_union_overview.json")
SRC_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v5")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v6")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v6")


SUBMISSION = {
    "created_at": "2026-05-05T10:53:12.787Z",
    "source_html": "file:///D:/phone2app/reports/compare_eval/final-wrong-union-horizontal-review-20260505-v5/final_wrong_union_horizontal_review.html#case-CEVAL-ABCD-027",
    "storage_key": "phone2app.finalWrongUnion.v5.reviewDecisions",
    "product_order": PRODUCTS,
    "decisions": [
        {"case_id": "MD-R07", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:50:39.940Z"},
        {"case_id": "MD-R07", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:50:41.321Z"},
        {"case_id": "MD-R07", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:50:42.655Z"},
        {"case_id": "MD-X04", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:48:43.473Z"},
        {"case_id": "MD-X04", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:48:45.251Z"},
        {"case_id": "MD-X04", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:48:46.958Z"},
        {"case_id": "MD-X08", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:48:59.992Z"},
        {"case_id": "MD-X08", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:01.515Z"},
        {"case_id": "MD-X08", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:02.706Z"},
        {"case_id": "MD-X11", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:10.621Z"},
        {"case_id": "MD-X11", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:11.788Z"},
        {"case_id": "MD-X11", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:13.295Z"},
        {"case_id": "MD-X20", "product": "团队版灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:28.359Z"},
        {"case_id": "MD-X20", "product": "移动灵犀", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:29.430Z"},
        {"case_id": "MD-X20", "product": "豆包", "action": "unscorable", "action_label": "不计分/需换题", "note": "", "saved_at": "2026-05-05T10:49:30.606Z"},
    ],
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def grouped_decisions() -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for item in SUBMISSION["decisions"]:
        grouped.setdefault(item["case_id"], {})[item["product"]] = item["action"]
    return grouped


def fully_unscorable_case_ids() -> set[str]:
    grouped = grouped_decisions()
    return {
        case_id
        for case_id, product_actions in grouped.items()
        if all(product_actions.get(product) == "unscorable" for product in PRODUCTS)
    }


def write_overview() -> dict[str, Any]:
    src = load_json(SRC_OVERVIEW)
    remove_ids = fully_unscorable_case_ids()
    removed = [row for row in src["rows"] if row.get("case_id") in remove_ids]
    rows = [row for row in src["rows"] if row.get("case_id") not in remove_ids]
    for idx, row in enumerate(rows, start=1):
        row["index"] = idx
    counts = {product: 0 for product in PRODUCTS}
    module_counts: dict[str, dict[str, int]] = {}
    for row in rows:
        module = row.get("module", "")
        module_counts.setdefault(module, {"union": 0, **{product: 0 for product in PRODUCTS}})
        module_counts[module]["union"] += 1
        for product in PRODUCTS:
            if row.get("status", {}).get(product) == "错":
                counts[product] += 1
                module_counts[module][product] += 1
    out = {
        **src,
        "counts": counts,
        "union_count": len(rows),
        "rows": rows,
        "applied_review_submission": SUBMISSION,
        "removed_as_unscorable_case_ids": sorted(remove_ids),
        "removed_rows": removed,
        "module_counts": module_counts,
    }
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_OVERVIEW_DIR / "review_submission.json").write_text(
        json.dumps(SUBMISSION, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 三产品最终不通过项并集概览 v6",
        "",
        "- 已应用人工提交：`MD-R07`、`MD-X04`、`MD-X08`、`MD-X11`、`MD-X20` 三家均转为不计分/需换题。",
        f"- 并集总行数：`{len(rows)}`",
        "",
        "| 产品 | 最终不通过数 |",
        "| --- | ---: |",
    ]
    for product in PRODUCTS:
        lines.append(f"| {product} | {counts[product]} |")
    lines.extend(["", "## 模块统计", "", "| 模块 | 并集题数 | 团队版灵犀错 | 移动灵犀错 | 豆包错 |", "| --- | ---: | ---: | ---: | ---: |"])
    for module, stat in module_counts.items():
        lines.append(f"| {module} | {stat['union']} | {stat['团队版灵犀']} | {stat['移动灵犀']} | {stat['豆包']} |")
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def remove_case_sections(html: str, case_ids: set[str]) -> str:
    for case_id in case_ids:
        html = re.sub(
            rf'<section class="case-card" id="case-{re.escape(case_id)}">.*?</section>',
            "",
            html,
            flags=re.S,
        )
        html = re.sub(
            rf'<a href="#case-{re.escape(case_id)}">.*?</a>',
            "",
            html,
            flags=re.S,
        )
    return html


def update_html(out: dict[str, Any]) -> None:
    if OUT_HTML_DIR.exists():
        shutil.rmtree(OUT_HTML_DIR)
    shutil.copytree(SRC_HTML_DIR, OUT_HTML_DIR)
    remove_ids = set(out["removed_as_unscorable_case_ids"])
    html_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review.html"
    text = html_path.read_text(encoding="utf-8")
    text = remove_case_sections(text, remove_ids)
    text = text.replace("三产品最终不通过项并集横向复核 v5", "三产品最终不通过项并集横向复核 v6")
    text = re.sub(r"共 <b>\d+</b> 行", f"共 <b>{out['union_count']}</b> 行", text, count=1)
    text = re.sub(r"<td>团队版灵犀</td><td>\d+</td>", f"<td>团队版灵犀</td><td>{out['counts']['团队版灵犀']}</td>", text, count=1)
    text = re.sub(r"<td>移动灵犀</td><td>\d+</td>", f"<td>移动灵犀</td><td>{out['counts']['移动灵犀']}</td>", text, count=1)
    text = re.sub(r"<td>豆包</td><td>\d+</td>", f"<td>豆包</td><td>{out['counts']['豆包']}</td>", text, count=1)
    text = re.sub(r"<tr><td>并集总行数</td><td>\d+</td></tr>", f"<tr><td>并集总行数</td><td>{out['union_count']}</td></tr>", text, count=1)
    text = re.sub(
        r"<div class=\"summary\">",
        "<div class=\"summary\">已应用人工提交：MD-R07、MD-X04、MD-X08、MD-X11、MD-X20 转不计分/需换题。 ",
        text,
        count=1,
    )
    # Keep the review UI, but isolate v6 localStorage from v5.
    text = text.replace("phone2app.finalWrongUnion.v5.reviewDecisions", "phone2app.finalWrongUnion.v6.reviewDecisions")
    html_path.write_text(text, encoding="utf-8")
    manifest_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review_manifest.json"
    manifest = load_json(manifest_path)
    manifest.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str((OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").resolve()),
            "union_count": out["union_count"],
            "counts": out["counts"],
            "applied_review_submission": SUBMISSION,
            "removed_as_unscorable_case_ids": out["removed_as_unscorable_case_ids"],
        }
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT_OVERVIEW_DIR / "final_wrong_union_overview.md", OUT_HTML_DIR / "final_wrong_union_horizontal_review.md")


def main() -> int:
    out = write_overview()
    update_html(out)
    print(f"HTML {OUT_HTML_DIR / 'final_wrong_union_horizontal_review.html'}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print(f"REMOVED {','.join(out['removed_as_unscorable_case_ids'])}")
    print(f"UNION {out['union_count']}")
    print(f"COUNTS {out['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
