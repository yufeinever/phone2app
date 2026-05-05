from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
SRC_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v9/final_wrong_union_overview.json")
SRC_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v9")
SRC_EMBEDDED_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v9-embedded")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v10")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v10")
OUT_EMBEDDED_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v10-embedded")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scored_payload() -> dict[str, Any]:
    payload = load_json(SRC_OVERVIEW)
    scope = dict(payload["test_scope"])
    effective_total = int(scope["effective_scored_cases"])
    excluded_count = int(scope["excluded_unscorable_case_count"])
    scope["scored_total_cases"] = effective_total
    scope["display_total_cases"] = effective_total
    scope["pass_wrong_text_definition"] = "x/y = 通过/不通过；总集和子集均按有效计分题数统计。"
    scope.pop("raw_total_cases", None)
    scope.pop("main_dialogue_cases", None)
    scope.pop("ceval_abcd_cases", None)
    payload["version"] = "v10"
    payload["created_at"] = datetime.now().isoformat(timespec="seconds")
    payload["test_scope"] = scope

    product_summary = {}
    for product, stat in payload["product_pass_wrong_summary"].items():
        wrong = int(stat["wrong"])
        passed = effective_total - wrong
        product_summary[product] = {
            "total": effective_total,
            "pass": passed,
            "wrong": wrong,
            "pass_wrong_text": f"{passed}/{wrong}",
            "accuracy_percent": round(passed / effective_total * 100, 1),
        }
    payload["product_pass_wrong_summary"] = product_summary

    module_scope_counts = {}
    for module, stat in payload["module_scope_counts"].items():
        effective = int(stat["effective_total"])
        row = {
            "total": effective,
            "excluded_unscorable": int(stat.get("raw_total", effective)) - effective,
            "union_wrong_cases": int(stat["union_wrong_cases"]),
        }
        for product in PRODUCTS:
            wrong = int(stat[f"{product}_wrong"])
            row[f"{product}_wrong"] = wrong
            row[f"{product}_pass"] = effective - wrong
        module_scope_counts[module] = row
    payload["module_scope_counts"] = module_scope_counts
    payload["display_policy"] = {
        "total_case_count_basis": "有效计分题数",
        "total_case_count": effective_total,
        "excluded_unscorable_case_count": excluded_count,
        "note": "所有总集和子集均使用 317 题有效计分口径。",
    }
    return payload


def write_overview(payload: dict[str, Any]) -> None:
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    scope = payload["test_scope"]
    lines = [
        "# 三产品最终不通过项并集概览 v10",
        "",
        f"- 应测题数：`{scope['display_total_cases']}`，按有效计分题数统计。",
        f"- 不计分/需换题：`{scope['excluded_unscorable_case_count']}` 题，不进入总集和子集分母。",
        f"- 当前 HTML 只展示最终不通过项并集：`{scope['wrong_union_rows']}` 行。",
        "- `x/y` 表示 `通过/不通过`。",
        "",
        "## 产品汇总",
        "",
        "| 产品 | 应测题数 | 通过/不通过 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for product, stat in payload["product_pass_wrong_summary"].items():
        lines.append(f"| {product} | {stat['total']} | {stat['pass_wrong_text']} | {stat['accuracy_percent']}% |")
    lines.extend(["", "## 模块统计", "", "| 模块 | 子集题数 | 并集不通过题数 | 团队版灵犀 通过/不通过 | 移动灵犀 通过/不通过 | 豆包 通过/不通过 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for module, stat in payload["module_scope_counts"].items():
        lines.append(
            f"| {module} | {stat['total']} | {stat['union_wrong_cases']} | "
            f"{stat['团队版灵犀_pass']}/{stat['团队版灵犀_wrong']} | {stat['移动灵犀_pass']}/{stat['移动灵犀_wrong']} | {stat['豆包_pass']}/{stat['豆包_wrong']} |"
        )
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def scope_html(payload: dict[str, Any]) -> str:
    scope = payload["test_scope"]
    product_rows = []
    for product, stat in payload["product_pass_wrong_summary"].items():
        product_rows.append(
            f"<tr><td>{product}</td><td>{stat['total']}</td><td><b>{stat['pass_wrong_text']}</b></td><td>{stat['accuracy_percent']}%</td></tr>"
        )
    module_rows = []
    for module, stat in payload["module_scope_counts"].items():
        module_rows.append(
            f"<tr><td>{module}</td><td>{stat['total']}</td><td>{stat['union_wrong_cases']}</td>"
            f"<td>{stat['团队版灵犀_pass']}/{stat['团队版灵犀_wrong']}</td>"
            f"<td>{stat['移动灵犀_pass']}/{stat['移动灵犀_wrong']}</td>"
            f"<td>{stat['豆包_pass']}/{stat['豆包_wrong']}</td></tr>"
        )
    removed = "、".join(scope["excluded_unscorable_case_ids"])
    return (
        '<div class="overview">'
        '<h2 class="overview-title">测试基本情况</h2>'
        '<div class="scope-grid">'
        f'<div><b>评测对象</b><span>{"、".join(PRODUCTS)}</span></div>'
        f'<div><b>应测题数</b><span>{scope["display_total_cases"]} 题</span></div>'
        f'<div><b>计分口径</b><span>不计分/需换题 {scope["excluded_unscorable_case_count"]} 题，不进入总集和子集</span></div>'
        f'<div><b>本页范围</b><span>最终不通过项并集 {scope["wrong_union_rows"]} 行；每行至少一家产品不通过</span></div>'
        '</div>'
        f'<p class="scope-note">口径：<b>x/y</b> 表示 <b>通过/不通过</b>；总集和子集均按有效计分题数统计。已剔除：{removed}。</p>'
        '<h2 class="overview-title">产品汇总</h2>'
        '<table><thead><tr><th>产品</th><th>应测题数</th><th>通过/不通过</th><th>通过率</th></tr></thead><tbody>'
        + "".join(product_rows)
        + '</tbody></table><br>'
        '<h2 class="overview-title">模块统计</h2>'
        '<table><thead><tr><th>模块</th><th>子集题数</th><th>并集不通过题数</th><th>团队版灵犀 通过/不通过</th><th>移动灵犀 通过/不通过</th><th>豆包 通过/不通过</th></tr></thead><tbody>'
        + "".join(module_rows)
        + "</tbody></table></div>"
    )


def update_html(src_dir: Path, out_dir: Path, payload: dict[str, Any], embedded: bool) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src_dir, out_dir)
    filename = "final_wrong_union_horizontal_review_embedded.html" if embedded else "final_wrong_union_horizontal_review.html"
    html_path = out_dir / filename
    text = html_path.read_text(encoding="utf-8")
    old_title = "三产品最终不通过项并集横向复核 v9 单文件版" if embedded else "三产品最终不通过项并集横向复核 v9"
    new_title = "三产品最终不通过项并集横向复核 v10 单文件版" if embedded else "三产品最终不通过项并集横向复核 v10"
    text = text.replace(old_title, new_title)
    text = text.replace("phone2app.finalWrongUnion.v9.reviewDecisions", "phone2app.finalWrongUnion.v10.reviewDecisions")
    text = re.sub(
        r'<div class="summary">.*?</div></header>',
        f'<div class="summary">本版统一使用有效计分口径：应测 <b>{payload["test_scope"]["display_total_cases"]}</b> 题，最终不通过项并集 <b>{payload["test_scope"]["wrong_union_rows"]}</b> 行。</div></header>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'<div class="overview">.*?</div><h2 class="module-heading"',
        scope_html(payload) + '<h2 class="module-heading"',
        text,
        count=1,
        flags=re.S,
    )
    html_path.write_text(text, encoding="utf-8")
    for manifest_path in out_dir.glob("*manifest.json"):
        manifest = load_json(manifest_path)
        manifest.update(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "version": "v10",
                "source": str((OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").resolve()),
                "test_scope": payload["test_scope"],
                "display_policy": payload["display_policy"],
                "product_pass_wrong_summary": payload["product_pass_wrong_summary"],
                "module_scope_counts": payload["module_scope_counts"],
            }
        )
        if manifest_path.name == "embedded_manifest.json":
            manifest["output_html"] = str(html_path.resolve())
            manifest["output_html_bytes"] = html_path.stat().st_size
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(OUT_OVERVIEW_DIR / "final_wrong_union_overview.md", out_dir / "final_wrong_union_horizontal_review.md")
    return html_path


def main() -> int:
    payload = scored_payload()
    write_overview(payload)
    html_path = update_html(SRC_HTML_DIR, OUT_HTML_DIR, payload, embedded=False)
    embedded_path = update_html(SRC_EMBEDDED_DIR, OUT_EMBEDDED_DIR, payload, embedded=True)
    print(f"HTML {html_path}")
    print(f"EMBEDDED {embedded_path}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print(f"SCOPE {json.dumps(payload['test_scope'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
