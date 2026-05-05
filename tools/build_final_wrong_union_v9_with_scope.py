from __future__ import annotations

import json
import re
import shutil
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
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
    "功能交互",
]

MAIN_CASES = Path("reports/product_eval/main-dialogue-300-v3.2-20260505/dialogue_cases.json")
CEVAL_CASES = Path("reports/product_eval/ceval-abcd-50-20260505/dialogue_cases.json")
SRC_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v8/final_wrong_union_overview.json")
SRC_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v8")
SRC_EMBEDDED_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v8-embedded")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v9")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v9")
OUT_EMBEDDED_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v9-embedded")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_module(case: dict[str, Any]) -> str:
    cid = case.get("case_id", "")
    module = case.get("module", "")
    if cid.startswith("CEVAL-"):
        return "学科考察"
    if module != "主对话-基础能力":
        return module
    if cid.startswith("MD-F"):
        return "上下文多轮" if cid in {"MD-F05", "MD-F06", "MD-F08"} else "功能交互"
    if cid.startswith("MD-I"):
        return "指令遵循"
    if cid.startswith("MD-K"):
        return "事实常识"
    if cid.startswith("MD-R"):
        return "中文语言" if cid == "MD-R11" else "逻辑推理"
    if cid.startswith("MD-Q"):
        return "数学推理"
    if cid.startswith("MD-C"):
        return "代码能力"
    if cid.startswith("MD-W"):
        return "指令遵循" if cid == "MD-W08" else "中文语言"
    if cid.startswith("MD-T"):
        return "安全红队" if cid in {"MD-T05", "MD-T06", "MD-T07"} else "事实常识"
    if cid.startswith("MD-S"):
        return "安全红队"
    return module


def module_denominators(removed_ids: set[str]) -> OrderedDict[str, dict[str, int]]:
    main_cases = load_json(MAIN_CASES)["results"]
    ceval_cases = load_json(CEVAL_CASES)["results"]
    all_cases = main_cases + ceval_cases
    raw = Counter(normalize_module(case) for case in all_cases)
    effective = Counter(normalize_module(case) for case in all_cases if case.get("case_id") not in removed_ids)
    ordered: OrderedDict[str, dict[str, int]] = OrderedDict()
    for module in MODULE_ORDER:
        if raw[module] or effective[module]:
            ordered[module] = {"raw_total": raw[module], "effective_total": effective[module]}
    for module in sorted(set(raw) | set(effective)):
        if module not in ordered:
            ordered[module] = {"raw_total": raw[module], "effective_total": effective[module]}
    return ordered


def build_enriched_payload() -> dict[str, Any]:
    overview = load_json(SRC_OVERVIEW)
    removed_ids = set(overview.get("removed_as_unscorable_case_ids", []))
    denominators = module_denominators(removed_ids)
    wrong_by_module = overview.get("module_counts", {})
    enriched_modules: OrderedDict[str, dict[str, int]] = OrderedDict()
    for module, totals in denominators.items():
        wrongs = wrong_by_module.get(module, {"union": 0, **{product: 0 for product in PRODUCTS}})
        row = dict(totals)
        row["union_wrong_cases"] = int(wrongs.get("union", 0))
        for product in PRODUCTS:
            wrong = int(wrongs.get(product, 0))
            row[f"{product}_wrong"] = wrong
            row[f"{product}_pass"] = row["effective_total"] - wrong
        enriched_modules[module] = row

    raw_total = sum(v["raw_total"] for v in enriched_modules.values())
    effective_total = sum(v["effective_total"] for v in enriched_modules.values())
    product_summary = OrderedDict()
    for product in PRODUCTS:
        wrong = int(overview["counts"][product])
        passed = effective_total - wrong
        product_summary[product] = {
            "raw_total": raw_total,
            "effective_total": effective_total,
            "pass": passed,
            "wrong": wrong,
            "pass_wrong_text": f"{passed}/{wrong}",
            "accuracy_percent": round(passed / effective_total * 100, 1) if effective_total else 0,
        }

    payload = dict(overview)
    payload["version"] = "v9"
    payload["created_at"] = datetime.now().isoformat(timespec="seconds")
    payload["test_scope"] = {
        "main_dialogue_cases": 274,
        "ceval_abcd_cases": 50,
        "raw_total_cases": raw_total,
        "excluded_unscorable_case_count": len(removed_ids),
        "excluded_unscorable_case_ids": sorted(removed_ids),
        "effective_scored_cases": effective_total,
        "wrong_union_rows": overview["union_count"],
        "products": PRODUCTS,
        "pass_wrong_text_definition": "x/y = 通过/不通过；分母为有效计分题数，不计分/需换题不进入通过或不通过。",
    }
    payload["product_pass_wrong_summary"] = product_summary
    payload["module_scope_counts"] = enriched_modules
    return payload


def write_overview(payload: dict[str, Any]) -> None:
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 三产品最终不通过项并集概览 v9",
        "",
        f"- 应测题数：主对话 `274` + 学科考察 `50` = `{payload['test_scope']['raw_total_cases']}`。",
        f"- 不计分/需换题：`{payload['test_scope']['excluded_unscorable_case_count']}` 题；有效计分题数：`{payload['test_scope']['effective_scored_cases']}`。",
        f"- 当前 HTML 只展示最终不通过项并集：`{payload['test_scope']['wrong_union_rows']}` 行。",
        "- `x/y` 表示 `通过/不通过`。",
        "",
        "## 产品汇总",
        "",
        "| 产品 | 应测题数 | 有效计分题数 | 通过/不通过 | 通过率 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for product, stat in payload["product_pass_wrong_summary"].items():
        lines.append(f"| {product} | {stat['raw_total']} | {stat['effective_total']} | {stat['pass_wrong_text']} | {stat['accuracy_percent']}% |")
    lines.extend(["", "## 模块统计", "", "| 模块 | 子集题量 应测/有效 | 并集不通过题数 | 团队版灵犀 通过/不通过 | 移动灵犀 通过/不通过 | 豆包 通过/不通过 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for module, stat in payload["module_scope_counts"].items():
        lines.append(
            f"| {module} | {stat['raw_total']}/{stat['effective_total']} | {stat['union_wrong_cases']} | "
            f"{stat['团队版灵犀_pass']}/{stat['团队版灵犀_wrong']} | {stat['移动灵犀_pass']}/{stat['移动灵犀_wrong']} | {stat['豆包_pass']}/{stat['豆包_wrong']} |"
        )
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def scope_html(payload: dict[str, Any]) -> str:
    scope = payload["test_scope"]
    product_rows = []
    for product, stat in payload["product_pass_wrong_summary"].items():
        product_rows.append(
            f"<tr><td>{product}</td><td>{stat['raw_total']}</td><td>{stat['effective_total']}</td>"
            f"<td><b>{stat['pass_wrong_text']}</b></td><td>{stat['accuracy_percent']}%</td></tr>"
        )
    module_rows = []
    for module, stat in payload["module_scope_counts"].items():
        module_rows.append(
            f"<tr><td>{module}</td><td>{stat['raw_total']}/{stat['effective_total']}</td><td>{stat['union_wrong_cases']}</td>"
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
        f'<div><b>应测题数</b><span>主对话 274 + 学科考察 50 = {scope["raw_total_cases"]}</span></div>'
        f'<div><b>有效计分</b><span>{scope["effective_scored_cases"]} 题；不计分/需换题 {scope["excluded_unscorable_case_count"]} 题</span></div>'
        f'<div><b>本页范围</b><span>最终不通过项并集 {scope["wrong_union_rows"]} 行；每行至少一家产品不通过</span></div>'
        '</div>'
        f'<p class="scope-note">口径：<b>x/y</b> 表示 <b>通过/不通过</b>；不计分/需换题不进入通过或不通过。已剔除：{removed}。</p>'
        '<h2 class="overview-title">产品汇总</h2>'
        '<table><thead><tr><th>产品</th><th>应测题数</th><th>有效计分题数</th><th>通过/不通过</th><th>通过率</th></tr></thead><tbody>'
        + "".join(product_rows)
        + '</tbody></table><br>'
        '<h2 class="overview-title">模块统计</h2>'
        '<table><thead><tr><th>模块</th><th>子集题量 应测/有效</th><th>并集不通过题数</th><th>团队版灵犀 通过/不通过</th><th>移动灵犀 通过/不通过</th><th>豆包 通过/不通过</th></tr></thead><tbody>'
        + "".join(module_rows)
        + "</tbody></table></div>"
    )


def update_html_file(src_dir: Path, out_dir: Path, payload: dict[str, Any], embedded: bool = False) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(src_dir, out_dir)
    name = "final_wrong_union_horizontal_review_embedded.html" if embedded else "final_wrong_union_horizontal_review.html"
    html_path = out_dir / name
    text = html_path.read_text(encoding="utf-8")
    old_title = "三产品最终不通过项并集横向复核 v8 单文件版" if embedded else "三产品最终不通过项并集横向复核 v8"
    new_title = "三产品最终不通过项并集横向复核 v9 单文件版" if embedded else "三产品最终不通过项并集横向复核 v9"
    text = text.replace(old_title, new_title)
    text = text.replace("phone2app.finalWrongUnion.v8.reviewDecisions", "phone2app.finalWrongUnion.v9.reviewDecisions")
    text = text.replace(
        ".overview{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:18px}",
        ".overview{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:18px}.overview-title{font-size:15px;margin:2px 0 10px}.scope-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:6px 0 10px}.scope-grid div{border:1px solid var(--line);background:#fbfcfe;border-radius:7px;padding:9px}.scope-grid b{display:block;font-size:12px;color:#344054;margin-bottom:4px}.scope-grid span{font-size:13px}.scope-note{font-size:13px;color:var(--muted);line-height:1.5;margin:8px 0 14px}",
    )
    text = re.sub(
        r'<div class="summary">.*?</div></header>',
        f'<div class="summary">本版补充测试基本情况与模块分母：应测 <b>{payload["test_scope"]["raw_total_cases"]}</b> 题，有效计分 <b>{payload["test_scope"]["effective_scored_cases"]}</b> 题，最终不通过项并集 <b>{payload["test_scope"]["wrong_union_rows"]}</b> 行。</div></header>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(r'<div class="overview">.*?</div><h2 class="module-heading"', scope_html(payload) + '<h2 class="module-heading"', text, count=1, flags=re.S)
    html_path.write_text(text, encoding="utf-8")

    manifest_candidates = list(out_dir.glob("*manifest.json"))
    for manifest_path in manifest_candidates:
        manifest = load_json(manifest_path)
        manifest.update(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "version": "v9",
                "source": str((OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").resolve()),
                "test_scope": payload["test_scope"],
                "product_pass_wrong_summary": payload["product_pass_wrong_summary"],
                "module_scope_counts": payload["module_scope_counts"],
            }
        )
        if manifest_path.name == "embedded_manifest.json":
            manifest["output_html"] = str(html_path.resolve())
            manifest["output_html_bytes"] = html_path.stat().st_size
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    shutil.copy2(OUT_OVERVIEW_DIR / "final_wrong_union_overview.md", out_dir / ("final_wrong_union_horizontal_review.md"))
    return html_path


def main() -> int:
    payload = build_enriched_payload()
    write_overview(payload)
    html_path = update_html_file(SRC_HTML_DIR, OUT_HTML_DIR, payload, embedded=False)
    embedded_path = update_html_file(SRC_EMBEDDED_DIR, OUT_EMBEDDED_DIR, payload, embedded=True)
    print(f"HTML {html_path}")
    print(f"EMBEDDED {embedded_path}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print(f"SCOPE {json.dumps(payload['test_scope'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
