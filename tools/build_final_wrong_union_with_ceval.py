from __future__ import annotations

import html
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
RUN_KEYS = {
    "团队版灵犀": "team_lingxi",
    "移动灵犀": "mobile_lingxi",
    "豆包": "doubao",
}
OLD_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v4")
OLD_OVERVIEW = Path("reports/compare_eval/final-wrong-union-overview-20260505-v4/final_wrong_union_overview.json")
CEVAL_RUN = Path("reports/compare_eval/rotating-main-dialogue-20260505-173100")
CEVAL_CASES = Path("reports/product_eval/ceval-abcd-50-20260505/dialogue_cases.json")
OUT_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v5")
OUT_OVERVIEW_DIR = Path("reports/compare_eval/final-wrong-union-overview-20260505-v5")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def md_cell(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|")


def first_turn(result: dict[str, Any]) -> dict[str, Any]:
    turns = result.get("turns") or []
    return turns[0] if turns else {}


def result_status(result: dict[str, Any] | None) -> str:
    if not result:
        return "缺失"
    return "错" if result.get("status") != "pass" else "对/非错"


def copy_asset(src: str, dst_name: str) -> str:
    if not src:
        return ""
    src_path = Path(src)
    if not src_path.is_absolute():
        src_path = Path.cwd() / src_path
    if not src_path.exists():
        return ""
    dst = OUT_HTML_DIR / "assets" / dst_name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dst)
    return f"assets/{dst_name}"


def answer_for(result: dict[str, Any] | None) -> str:
    if not result:
        return "未执行/未找到结果"
    turn = first_turn(result)
    return str(turn.get("actual") or result.get("error") or "")


def judge_for(result: dict[str, Any] | None, expected: str) -> str:
    if not result:
        return "未执行/未找到结果"
    turn = first_turn(result)
    status = result.get("status")
    detail = turn.get("evaluation_detail") or ""
    actual = turn.get("actual") or ""
    if status == "pass":
        return f"严格单选通过；标准答案 {expected}；实际回答 {actual}。{detail}"
    return f"严格单选不通过；标准答案 {expected}；实际回答 {actual or '空'}。{detail}"


def image_for(product: str, result: dict[str, Any] | None, case_id: str) -> str:
    if not result:
        return ""
    turn = first_turn(result)
    src = turn.get("response_screenshot") or result.get("error_screenshot") or turn.get("typed_screenshot") or ""
    suffix = RUN_KEYS[product]
    return copy_asset(src, f"{case_id}_{suffix}_1.png")


def build_ceval_rows() -> list[dict[str, Any]]:
    case_data = load_json(CEVAL_CASES)["results"]
    case_by_id = {case["case_id"]: case for case in case_data}
    runs: dict[str, dict[str, dict[str, Any]]] = {}
    for product, key in RUN_KEYS.items():
        path = CEVAL_RUN / "aggregates" / key / "cases.json"
        data = load_json(path)
        runs[product] = {item["case_id"]: item for item in data["results"]}

    rows: list[dict[str, Any]] = []
    for case_id in sorted(case_by_id):
        product_results = {product: runs[product].get(case_id) for product in PRODUCTS}
        if all((result and result.get("status") == "pass") for result in product_results.values()):
            continue
        case = case_by_id[case_id]
        expected = case.get("strict_expected") or case.get("expected_result") or case.get("answer", "")
        statuses = {product: result_status(product_results[product]) for product in PRODUCTS}
        wrong_reason = {
            product: judge_for(product_results[product], expected)
            for product in PRODUCTS
            if statuses[product] == "错"
        }
        rows.append(
            {
                "case_id": case_id,
                "module": "学科考察",
                "feature": case.get("feature") or case.get("ability") or "",
                "ability": case.get("ability") or "",
                "summary": case.get("summary") or case.get("question") or "",
                "input": first_turn(case).get("input") if case.get("turns") else case.get("input", ""),
                "expected": expected,
                "status": statuses,
                "wrong_reason": wrong_reason,
                "products": {
                    product: {
                        "actual": answer_for(product_results[product]),
                        "judge": judge_for(product_results[product], expected),
                        "status": statuses[product],
                        "screenshot": image_for(product, product_results[product], case_id),
                    }
                    for product in PRODUCTS
                },
            }
        )
    return rows


def product_label(product: str) -> str:
    return {"团队版灵犀": "灵犀", "移动灵犀": "移动", "豆包": "豆包"}[product]


def mini_nav(row: dict[str, Any]) -> str:
    chips = []
    for product in PRODUCTS:
        bad = row["status"][product] == "错"
        chips.append(f'<span class="mini {"bad" if bad else "ok"}">{product_label(product)}</span>')
    return f'<a href="#case-{esc(row["case_id"])}"><b>{esc(row["case_id"])}</b> {"".join(chips)}</a>'


def product_card(product: str, row: dict[str, Any]) -> str:
    item = row["products"][product]
    is_wrong = row["status"][product] == "错"
    badge = '<div class="badge fail">最终不通过</div>' if is_wrong else '<div class="badge compare">横向对照：非错</div>'
    reason = ""
    if is_wrong:
        reason = f'<div class="wrong-reason"><b>最终错误原因：</b>{esc(row["wrong_reason"].get(product, ""))}</div>'
    shot = item.get("screenshot") or ""
    if shot:
        fig = (
            f'<div class="shots"><figure><a href="{esc(shot)}" target="_blank">'
            f'<img src="{esc(shot)}" alt="{esc(product)} {esc(row["case_id"])}"></a>'
            f'<figcaption>{esc(Path(shot).name)}</figcaption></figure></div>'
        )
    else:
        fig = '<div class="missing">未找到截图</div>'
    return (
        f'<div class="prod-card"><h3>{esc(product)}</h3>{badge}{reason}'
        f'<div class="label">答案摘要</div><div class="answer">{esc(item.get("actual", ""))}</div>'
        f'<div class="label">我们的判断</div><div class="judge">{esc(item.get("judge", ""))}</div>{fig}</div>'
    )


def case_card(index: int, row: dict[str, Any]) -> str:
    chips = []
    for product in PRODUCTS:
        bad = row["status"][product] == "错"
        chips.append(f'<span class="status-chip {"wrong" if bad else "ok"}">{product_label(product)}：{"错" if bad else "非错"}</span>')
    products = "".join(product_card(product, row) for product in PRODUCTS)
    state = "；".join(f"{product}:{row['status'][product]}" for product in PRODUCTS)
    return (
        f'<section class="case-card" id="case-{esc(row["case_id"])}">'
        f'<div class="case-head"><div class="case-no">#{index}</div><div class="case-id">{esc(row["case_id"])}</div>'
        f'<h3>{esc(row["feature"])} · {esc(row["summary"])}</h3><div class="case-status">{"".join(chips)}</div></div>'
        f'<div class="case-meta"><div><b>题目输入</b><pre>{esc(row["input"])}</pre></div>'
        f'<div><b>预期/判分规则</b><pre>{esc(row["expected"])}</pre></div>'
        f'<div><b>本题最终状态</b><pre>{esc(state)}</pre></div></div>'
        f'<div class="products">{products}</div></section>'
    )


def build_module_html(rows: list[dict[str, Any]], start_index: int) -> str:
    cards = "\n".join(case_card(start_index + idx, row) for idx, row in enumerate(rows))
    return f'<h2 class="module-heading" id="module-学科考察">学科考察 <span>{len(rows)} 题</span></h2>\n{cards}'


def build_nav(rows: list[dict[str, Any]]) -> str:
    return (
        '<div class="nav-module"><a class="module-link" href="#module-学科考察">学科考察 '
        f'<span>{len(rows)}</span></a><div class="nav-cases">{"".join(mini_nav(row) for row in rows)}</div></div>'
    )


def update_html(rows: list[dict[str, Any]], old_union: int, old_counts: dict[str, int]) -> None:
    html_path = OUT_HTML_DIR / "final_wrong_union_horizontal_review.html"
    text = html_path.read_text(encoding="utf-8")
    new_counts = old_counts.copy()
    for product in PRODUCTS:
        new_counts[product] += sum(1 for row in rows if row["status"][product] == "错")
    new_union = old_union + len(rows)
    text = text.replace("三产品最终不通过项并集横向复核 v4", "三产品最终不通过项并集横向复核 v5")
    text = text.replace(f"共 <b>{old_union}</b> 行", f"共 <b>{new_union}</b> 行")
    text = text.replace("<td>团队版灵犀</td><td>14</td>", f"<td>团队版灵犀</td><td>{new_counts['团队版灵犀']}</td>")
    text = text.replace("<td>移动灵犀</td><td>25</td>", f"<td>移动灵犀</td><td>{new_counts['移动灵犀']}</td>")
    text = text.replace("<td>豆包</td><td>10</td>", f"<td>豆包</td><td>{new_counts['豆包']}</td>")
    text = text.replace(f"<tr><td>并集总行数</td><td>{old_union}</td></tr>", f"<tr><td>并集总行数</td><td>{new_union}</td></tr>")
    module_row = (
        f"<tr><td>学科考察</td><td>{len(rows)}</td>"
        f"<td>{sum(1 for row in rows if row['status']['团队版灵犀'] == '错')}</td>"
        f"<td>{sum(1 for row in rows if row['status']['移动灵犀'] == '错')}</td>"
        f"<td>{sum(1 for row in rows if row['status']['豆包'] == '错')}</td></tr>"
    )
    marker = "</tbody></table></div><h2 class=\"module-heading\""
    text = text.replace(marker, module_row + marker, 1)
    text = text.replace("</aside><main>", build_nav(rows) + "</aside><main>", 1)
    text = text.replace("</main></div><a class=\"backtop\"", build_module_html(rows, old_union + 1) + "</main></div><a class=\"backtop\"", 1)
    html_path.write_text(text, encoding="utf-8")

    manifest = load_json(OLD_HTML_DIR / "final_wrong_union_horizontal_review_manifest.json")
    manifest.update(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source": str((OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").resolve()),
            "union_count": new_union,
            "counts": new_counts,
            "ceval_module": "学科考察",
            "ceval_wrong_union_count": len(rows),
            "ceval_run": str(CEVAL_RUN.resolve()),
        }
    )
    (OUT_HTML_DIR / "final_wrong_union_horizontal_review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update_overview(rows: list[dict[str, Any]], old: dict[str, Any]) -> None:
    OUT_OVERVIEW_DIR.mkdir(parents=True, exist_ok=True)
    old_rows = old["rows"]
    new_rows = []
    for idx, row in enumerate(old_rows + rows, start=1):
        clean = {k: v for k, v in row.items() if k != "products"}
        clean["index"] = idx
        if clean.get("module") == "主对话-标准选择题":
            clean["module"] = "学科考察"
        new_rows.append(clean)
    counts = old["counts"].copy()
    for product in PRODUCTS:
        counts[product] += sum(1 for row in rows if row["status"][product] == "错")
    payload = {
        **old,
        "counts": counts,
        "union_count": len(new_rows),
        "rows": new_rows,
        "ceval_module": "学科考察",
        "ceval_wrong_union_count": len(rows),
        "ceval_run": str(CEVAL_RUN.resolve()),
    }
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 三产品最终不通过项并集概览 v5",
        "",
        f"- 并集总行数：`{len(new_rows)}`",
        f"- 新增模块：`学科考察`，`{len(rows)}` 行",
        "",
        "| 产品 | 最终不通过数 |",
        "| --- | ---: |",
    ]
    for product in PRODUCTS:
        lines.append(f"| {product} | {counts[product]} |")
    lines.extend(["", "## 学科考察新增错题", "", "| 用例 | 子类 | 标准答案 | 团队版灵犀 | 移动灵犀 | 豆包 | 摘要 |", "| --- | --- | --- | --- | --- | --- | --- |"])
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {md_cell(row['feature'])} | {row['expected']} | "
            f"{row['status']['团队版灵犀']} | {row['status']['移动灵犀']} | {row['status']['豆包']} | {md_cell(row['summary'])} |"
        )
    (OUT_OVERVIEW_DIR / "final_wrong_union_overview.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    old = load_json(OLD_OVERVIEW)
    if OUT_HTML_DIR.exists():
        shutil.rmtree(OUT_HTML_DIR)
    shutil.copytree(OLD_HTML_DIR, OUT_HTML_DIR)
    rows = build_ceval_rows()
    update_overview(rows, old)
    update_html(rows, int(old["union_count"]), dict(old["counts"]))
    print(f"HTML {OUT_HTML_DIR / 'final_wrong_union_horizontal_review.html'}")
    print(f"OVERVIEW {OUT_OVERVIEW_DIR / 'final_wrong_union_overview.md'}")
    print(f"ADDED {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
