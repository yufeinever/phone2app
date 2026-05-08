from __future__ import annotations

import html
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


PRODUCTS = ["团队版灵犀", "移动灵犀", "豆包"]
DISPLAY_REPLACEMENTS = {
    "团队版灵犀": "灵犀",
}
WRONG = "错"
OVERVIEW_PATH = Path(
    "reports/compare_eval/final-wrong-union-overview-20260505-v10/final_wrong_union_overview.json"
)
SOURCE_HTML_DIR = Path("reports/compare_eval/final-wrong-union-horizontal-review-20260505-v10")
SOURCE_HTML_PATH = SOURCE_HTML_DIR / "final_wrong_union_horizontal_review.html"
SOURCE_ASSET_DIR = SOURCE_HTML_DIR / "assets"
OUT_DIR = Path("reports/compare_eval/final-wrong-union-analysis-20260505-v1")
OUT_ASSET_DIR = OUT_DIR / "assets"


CASE_SELECTION = [
    {
        "case_id": "MD-X05",
        "angle": "必要条件反推",
        "why": "同一条简单逻辑链里，团队版灵犀给出“无法确定”，而移动灵犀和豆包能直接推出结论，适合说明基础推理的稳定性差异。",
        "takeaway": "团队版灵犀在充分必要条件类题目上出现核心结论反向，属于低噪声、解释力强的独有失败。",
    },
    {
        "case_id": "MD-HF02",
        "angle": "真假话推理",
        "why": "团队版灵犀通过，移动灵犀和豆包同时错，能够区分同类逻辑题中产品间的稳定性差异。",
        "takeaway": "移动灵犀与豆包在约束枚举类逻辑题上都可能跳过完整校验，团队版灵犀此题表现更稳。",
    },
    {
        "case_id": "MD-EX-L15",
        "angle": "条件链逆推",
        "why": "团队版灵犀和移动灵犀都未完整推出非B与非A，豆包正确，是逻辑链条完整性的代表样本。",
        "takeaway": "团队版灵犀和移动灵犀在多步条件链上有共同弱点，错误不是格式问题，而是推理链缺失。",
    },
    {
        "case_id": "CEVAL-ABCD-019",
        "angle": "三者共同学科误判",
        "why": "三款产品在同一道历史地理单选题上都选错，适合说明学科考察并不是某一家产品的孤立问题。",
        "takeaway": "学科知识题存在共同压力点，不能只用总体通过率判断产品能力，需要单独观察知识密集型题目。",
    },
    {
        "case_id": "CEVAL-ABCD-027",
        "angle": "语言填空",
        "why": "团队版灵犀和移动灵犀同错，豆包正确，能体现中文语境和选项辨析上的差异。",
        "takeaway": "豆包在部分语文类单选上更稳，但同一模块内仍有其他独有失败，不能简单归纳为全面领先。",
    },
    {
        "case_id": "CEVAL-ABCD-033",
        "angle": "高等数学单选",
        "why": "豆包独有错误，团队版灵犀与移动灵犀正确，用来抵消“豆包总体最好就各维度都最好”的误读。",
        "takeaway": "豆包总体错误数少，但在数学学科题上仍会出现明确选项偏差。",
    },
    {
        "case_id": "MD-I03",
        "angle": "显性禁用词约束",
        "why": "题目要求回答中不能出现指定词，豆包直接违反，属于非常直观的指令遵循失败。",
        "takeaway": "豆包在自然回答质量之外，需要关注硬约束执行，特别是禁用词、格式和边界声明。",
    },
    {
        "case_id": "MD-Q01",
        "angle": "基础算术",
        "why": "移动灵犀独有错误，其他两家均输出 103，能够说明低复杂度计算的可靠性差异。",
        "takeaway": "移动灵犀的失败并非只集中在复杂推理，在基础算术上也有低级错误样本。",
    },
    {
        "case_id": "MD-EX-C05",
        "angle": "多轮否定更新",
        "why": "移动灵犀未吸收用户后续修正，把最终状态答成“完成”而不是“提前”。",
        "takeaway": "移动灵犀在多轮上下文更新和用户最新约束优先级上需要重点复测。",
    },
    {
        "case_id": "MD-EX-S17",
        "angle": "工具调用边界",
        "why": "豆包虚假声称已经发短信，属于外部动作边界问题，比普通答错更值得产品侧关注。",
        "takeaway": "豆包虽总体通过率最高，但在工具/外部动作声明上暴露高风险边界问题。",
    },
]


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def apply_display_names(text: str) -> str:
    for raw, display in DISPLAY_REPLACEMENTS.items():
        text = text.replace(raw, display)
    return text


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def product_slug(product: str) -> str:
    return {
        "团队版灵犀": "team_lingxi",
        "移动灵犀": "mobile_lingxi",
        "豆包": "doubao",
    }[product]


def is_wrong(status: str) -> bool:
    return status == WRONG


def bad_products(row: dict[str, Any]) -> list[str]:
    return [product for product in PRODUCTS if is_wrong(row["status"].get(product, ""))]


def pattern_label(bad: list[str]) -> str:
    if len(bad) == 1:
        return f"仅{bad[0]}错"
    if len(bad) == len(PRODUCTS):
        return "三者共同错"
    return " + ".join(bad) + "错"


def short(text: str, limit: int = 180) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def extract_case_details() -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(SOURCE_HTML_PATH.read_text(encoding="utf-8"), "html.parser")
    details: dict[str, dict[str, Any]] = {}
    for section in soup.select("section.case-card"):
        case_id = section.get("id", "").removeprefix("case-")
        if not case_id:
            continue
        title = section.select_one(".case-head h3")
        product_details: dict[str, Any] = {}
        for card in section.select(".prod-card"):
            name_node = card.find("h3")
            if not name_node:
                continue
            product = name_node.get_text(" ", strip=True)
            product_details[product] = {
                "badge": text_of(card.select_one(".badge")),
                "wrong_reason": text_of(card.select_one(".wrong-reason")).removeprefix("最终错误原因：").strip(),
                "answer": text_of(card.select_one(".answer")),
                "judge": text_of(card.select_one(".judge")),
                "images": [img.get("src", "") for img in card.select("img") if img.get("src")],
            }
        details[case_id] = {
            "title": text_of(title),
            "products": product_details,
        }
    return details


def text_of(node: Any) -> str:
    return "" if node is None else node.get_text("\n", strip=True)


def compute_stats(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rows"]
    module_union: Counter[str] = Counter()
    module_wrong: dict[str, Counter[str]] = defaultdict(Counter)
    patterns: Counter[tuple[str, ...]] = Counter()
    unique_wrong: Counter[str] = Counter()
    shared_pairs: Counter[tuple[str, str]] = Counter()

    for row in rows:
        bad = bad_products(row)
        module_union[row["module"]] += 1
        patterns[tuple(bad)] += 1
        for product in bad:
            module_wrong[row["module"]][product] += 1
        if len(bad) == 1:
            unique_wrong[bad[0]] += 1
        for i, left in enumerate(bad):
            for right in bad[i + 1 :]:
                shared_pairs[tuple(sorted((left, right), key=PRODUCTS.index))] += 1

    return {
        "module_union": module_union,
        "module_wrong": module_wrong,
        "patterns": patterns,
        "unique_wrong": unique_wrong,
        "shared_pairs": shared_pairs,
    }


def copy_case_assets(case_ids: list[str]) -> dict[str, str]:
    OUT_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for case_id in case_ids:
        for src in SOURCE_ASSET_DIR.glob(f"{case_id}_*.png"):
            dest = OUT_ASSET_DIR / src.name
            shutil.copy2(src, dest)
            copied[f"assets/{src.name}"] = f"assets/{src.name}"
    return copied


def product_summary_html(payload: dict[str, Any], stats: dict[str, Any]) -> str:
    summary = payload["product_pass_wrong_summary"]
    rows = []
    for product in PRODUCTS:
        item = summary[product]
        wrong = item["wrong"]
        rows.append(
            f"""
            <div class="metric product-{product_slug(product)}">
              <div class="metric-label">{esc(product)}</div>
              <div class="metric-main">{esc(item["accuracy_percent"])}%</div>
              <div class="metric-sub">{esc(item["pass_wrong_text"])} 通过/不通过</div>
              <div class="bar"><span style="width:{wrong / max(x["wrong"] for x in summary.values()) * 100:.1f}%"></span></div>
              <div class="metric-foot">独有失败 {stats["unique_wrong"].get(product, 0)} 题</div>
            </div>
            """
        )
    return "\n".join(rows)


def overlap_html(stats: dict[str, Any]) -> str:
    patterns = stats["patterns"]
    ordered = [
        ("仅团队版灵犀错", ("团队版灵犀",)),
        ("仅移动灵犀错", ("移动灵犀",)),
        ("仅豆包错", ("豆包",)),
        ("团队版灵犀 + 移动灵犀共同错", ("团队版灵犀", "移动灵犀")),
        ("移动灵犀 + 豆包共同错", ("移动灵犀", "豆包")),
        ("团队版灵犀 + 豆包共同错", ("团队版灵犀", "豆包")),
        ("三者共同错", tuple(PRODUCTS)),
    ]
    max_count = max(patterns.values()) if patterns else 1
    rows = []
    for label, key in ordered:
        count = patterns.get(key, 0)
        rows.append(
            f"""
            <tr>
              <td>{esc(label)}</td>
              <td class="num">{count}</td>
              <td><div class="track"><span style="width:{count / max_count * 100:.1f}%"></span></div></td>
            </tr>
            """
        )
    return "\n".join(rows)


def module_heatmap_html(payload: dict[str, Any], stats: dict[str, Any]) -> str:
    module_scope = payload["module_scope_counts"]
    module_union = stats["module_union"]
    module_wrong = stats["module_wrong"]
    max_wrong = max((module_wrong[module].get(product, 0) for module in module_union for product in PRODUCTS), default=1)
    rows = []
    for module, union_count in module_union.most_common():
        counts = [module_wrong[module].get(product, 0) for product in PRODUCTS]
        top = max(counts)
        top_products = [product for product, wrong in zip(PRODUCTS, counts) if wrong == top and wrong > 0]
        second = sorted(counts, reverse=True)[1] if len(counts) > 1 else 0
        if len(top_products) == len(PRODUCTS):
            observation = "三者压力接近"
        elif len(top_products) > 1:
            observation = "、".join(top_products) + "偏高"
        elif top >= second + 2:
            observation = f"{top_products[0]}明显偏高"
        else:
            observation = f"{top_products[0]}略高" if top_products else "无明显差异"
        cells = []
        for product in PRODUCTS:
            wrong = module_wrong[module].get(product, 0)
            total = module_scope[module]["total"]
            rate = wrong / total * 100
            cells.append(
                f"""
                <td class="num-cell"><b>{wrong}</b><div class="mini-track"><span style="width:{wrong / max_wrong * 100:.1f}%"></span></div></td>
                <td class="rate-cell">{rate:.1f}%</td>
                """
            )
        rows.append(
            f"""
            <tr>
              <td class="module-name"><b>{esc(module)}</b></td>
              <td class="union-cell">{union_count}</td>
              {''.join(cells)}
              <td class="observe">{esc(observation)}</td>
            </tr>
            """
        )
    return "\n".join(rows)


def case_html(
    selection: dict[str, str],
    row_by_id: dict[str, dict[str, Any]],
    details_by_id: dict[str, dict[str, Any]],
) -> str:
    case_id = selection["case_id"]
    row = row_by_id[case_id]
    details = details_by_id.get(case_id, {})
    bad = bad_products(row)
    products = details.get("products", {})
    product_blocks = []
    for product in PRODUCTS:
        product_detail = products.get(product, {})
        wrong = product in bad
        img_src = ""
        for candidate in product_detail.get("images", []):
            if candidate.startswith("assets/"):
                img_src = candidate
                break
        product_blocks.append(
            f"""
            <div class="product-mini {'wrong' if wrong else 'pass'}">
              <div class="product-mini-head">
                <b>{esc(product)}</b>
                <span>{'未通过' if wrong else '通过'}</span>
              </div>
              <div class="answer-line"><em>答案</em>{esc(short(product_detail.get("answer", ""), 110))}</div>
              <div class="judge-line">{esc(short(product_detail.get("wrong_reason") or product_detail.get("judge", ""), 150))}</div>
              {f'<a class="shot-link" href="{esc(img_src)}" target="_blank"><img src="{esc(img_src)}" alt="{esc(product)} {esc(case_id)} 截图"></a>' if img_src else ''}
            </div>
            """
        )
    return f"""
    <article class="case">
      <div class="case-kicker">{esc(row["module"])} / {esc(selection["angle"])}</div>
      <div class="case-title-row">
        <h3>{esc(case_id)} · {esc(short(row.get("summary") or details.get("title", ""), 90))}</h3>
        <span class="pattern">{esc(pattern_label(bad))}</span>
      </div>
      <p class="case-why"><b>为什么选它：</b>{esc(selection["why"])}</p>
      <p class="case-takeaway"><b>分析判断：</b>{esc(selection["takeaway"])}</p>
      <div class="product-grid">{''.join(product_blocks)}</div>
    </article>
    """


def markdown_report(payload: dict[str, Any], stats: dict[str, Any]) -> str:
    summary = payload["product_pass_wrong_summary"]
    lines = [
        "# 三产品能力评估分析报告",
        "",
        "基于最终不通过项并集抽样分析，不替代全量逐题复核报告。",
        "",
        "## 关键结论",
        "",
        f"- 豆包总体通过率最高：{summary['豆包']['pass_wrong_text']}，通过率 {summary['豆包']['accuracy_percent']}%。",
        f"- 移动灵犀最终不通过最多：{summary['移动灵犀']['wrong']} 题；独有失败 {stats['unique_wrong'].get('移动灵犀', 0)} 题。",
        f"- 团队版灵犀与移动灵犀共同失败最多：{stats['shared_pairs'].get(('团队版灵犀', '移动灵犀'), 0)} 题。",
        "- 学科考察和逻辑推理是最主要的差异观察区。",
        "",
        "## 入选代表案例",
        "",
    ]
    for item in CASE_SELECTION:
        row = next(row for row in payload["rows"] if row["case_id"] == item["case_id"])
        lines.append(f"- {item['case_id']}：{row['module']} / {item['angle']}。{item['takeaway']}")
    return apply_display_names("\n".join(lines) + "\n")


def render_html(payload: dict[str, Any], stats: dict[str, Any], details_by_id: dict[str, dict[str, Any]]) -> str:
    row_by_id = {row["case_id"]: row for row in payload["rows"]}
    case_ids = [item["case_id"] for item in CASE_SELECTION]
    case_sections = "\n".join(case_html(item, row_by_id, details_by_id) for item in CASE_SELECTION)
    generated = datetime.now().isoformat(timespec="seconds")
    return apply_display_names(f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>三产品能力评估分析报告</title>
<style>
:root {{
  --bg: #f5f6f8;
  --panel: #ffffff;
  --text: #172033;
  --muted: #5f6b7a;
  --line: #d9dee7;
  --red: #b42318;
  --green: #067647;
  --amber: #b54708;
  --blue: #175cd3;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; }}
a {{ color: var(--blue); }}
.page {{ max-width: 1380px; margin: 0 auto; padding: 28px 28px 56px; }}
.hero {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(340px, .65fr); gap: 24px; align-items: end; padding: 26px 0 22px; border-bottom: 1px solid var(--line); }}
.eyebrow {{ color: var(--muted); font-size: 13px; font-weight: 700; letter-spacing: 0; }}
h1 {{ margin: 8px 0 10px; font-size: 34px; line-height: 1.18; }}
.lead {{ margin: 0; color: #344054; line-height: 1.7; font-size: 15px; }}
.hero-note {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; color: #344054; line-height: 1.6; }}
.metric-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 22px 0; }}
.metric {{ background: var(--panel); border: 1px solid var(--line); border-top: 4px solid #667085; border-radius: 8px; padding: 16px; min-width: 0; }}
.product-team_lingxi {{ border-top-color: #175cd3; }}
.product-mobile_lingxi {{ border-top-color: #b54708; }}
.product-doubao {{ border-top-color: #067647; }}
.metric-label {{ font-size: 14px; font-weight: 700; color: #344054; }}
.metric-main {{ font-size: 32px; font-weight: 800; margin-top: 8px; }}
.metric-sub, .metric-foot {{ color: var(--muted); font-size: 13px; margin-top: 6px; }}
.bar, .track {{ height: 8px; background: #eef2f7; border-radius: 999px; overflow: hidden; margin-top: 12px; }}
.bar span, .track span {{ display: block; height: 100%; background: var(--red); border-radius: inherit; }}
.section {{ margin-top: 26px; }}
.section h2 {{ margin: 0 0 12px; font-size: 21px; }}
.analysis-grid {{ display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 18px; }}
.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
.panel p {{ margin: 0 0 10px; color: #344054; line-height: 1.65; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: middle; }}
th {{ background: #f0f3f8; color: #344054; }}
td.num {{ font-weight: 800; font-size: 16px; width: 62px; }}
.table-scroll {{ overflow-x: auto; }}
.module-table {{ min-width: 1060px; }}
.module-table th {{ text-align: center; white-space: nowrap; }}
.module-table th:first-child, .module-table td:first-child, .module-table .observe {{ text-align: left; }}
.module-table .subhead th {{ font-size: 12px; color: var(--muted); background: #f8fafc; }}
.module-name b {{ display: block; font-size: 14px; }}
.union-cell {{ text-align: center; font-weight: 800; }}
.num-cell {{ text-align: right; font-variant-numeric: tabular-nums; width: 72px; }}
.num-cell b {{ display: block; font-size: 18px; }}
.rate-cell {{ text-align: right; color: #344054; font-variant-numeric: tabular-nums; width: 72px; }}
.mini-track {{ height: 5px; background: #eef2f7; border-radius: 999px; overflow: hidden; margin-top: 5px; }}
.mini-track span {{ display: block; height: 100%; background: var(--red); border-radius: inherit; }}
.observe {{ color: #344054; min-width: 140px; }}
td span {{ display: block; color: var(--muted); font-size: 12px; margin-top: 2px; }}
.insights {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
.insight {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }}
.insight h3 {{ margin: 0 0 8px; font-size: 15px; }}
.insight p {{ margin: 0; color: #344054; line-height: 1.6; font-size: 13px; }}
.case {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 18px; margin: 18px 0 22px; }}
.case-kicker {{ color: var(--muted); font-size: 12px; font-weight: 700; }}
.case-title-row {{ display: flex; gap: 12px; align-items: start; justify-content: space-between; margin-top: 6px; }}
.case h3 {{ margin: 0; font-size: 18px; line-height: 1.35; }}
.pattern {{ flex: 0 0 auto; border: 1px solid #fecdca; background: #fff5f5; color: var(--red); border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 800; }}
.case-why, .case-takeaway {{ margin: 10px 0 0; color: #344054; line-height: 1.65; font-size: 14px; }}
.product-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 16px; }}
.product-mini {{ border: 1px solid var(--line); border-top: 4px solid #98a2b3; border-radius: 8px; padding: 12px; background: #ffffff; min-width: 0; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
.product-mini.pass {{ border-top-color: var(--green); }}
.product-mini.wrong {{ border-color: #fecdca; border-top-color: var(--red); background: #fffdfd; }}
.product-mini-head {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; }}
.product-mini-head span {{ font-size: 12px; font-weight: 800; color: var(--green); }}
.product-mini.wrong .product-mini-head span {{ color: var(--red); }}
.answer-line, .judge-line {{ margin-top: 8px; color: #344054; line-height: 1.5; font-size: 13px; overflow-wrap: anywhere; }}
.answer-line em {{ font-style: normal; color: var(--muted); margin-right: 6px; font-weight: 700; }}
.shot-link {{ display: block; margin-top: 12px; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; background: #f8fafc; }}
.shot-link img {{ display: block; width: 100%; height: 430px; object-fit: contain; background: #f8fafc; }}
.shot-link:hover {{ border-color: #98a2b3; }}
.appendix {{ color: var(--muted); font-size: 13px; line-height: 1.6; }}
@media (max-width: 1050px) {{
  .hero, .analysis-grid, .metric-grid, .insights, .product-grid {{ grid-template-columns: 1fr; }}
  .page {{ padding: 18px; }}
  h1 {{ font-size: 28px; }}
  .shot-link img {{ height: 520px; }}
}}
</style>
</head>
<body>
<main class="page">
  <section class="hero">
    <div>
      <div class="eyebrow">基于最终不通过项并集的差异样本分析 / 生成时间 {esc(generated)}</div>
      <h1>三产品能力评估分析报告</h1>
      <p class="lead">本报告不再复刻全量测试证据，而是从 45 个最终不通过并集样本中提炼差异结构，并挑选 {len(case_ids)} 个代表案例说明产品能力边界。全量逐题证据仍保留为附录。</p>
    </div>
    <div class="hero-note">
      评估口径：有效计分题数 {esc(payload["test_scope"]["display_total_cases"])} 题；剔除不计分/需换题 {esc(payload["test_scope"]["excluded_unscorable_case_count"])} 题。这里的“错”指最终复核后未通过，不等同于截图或初判的原始状态。
    </div>
  </section>

  <section class="metric-grid">
    {product_summary_html(payload, stats)}
  </section>

  <section class="section analysis-grid">
    <div class="panel">
      <h2>差异结论</h2>
      <p><b>豆包总体领先。</b>豆包最终不通过 14 题，通过率 95.6%，是三者中总量表现最好的产品。</p>
      <p><b>移动灵犀失败最多。</b>移动灵犀最终不通过 24 题，其中独有失败 {stats["unique_wrong"].get("移动灵犀", 0)} 题，短板不仅在复杂逻辑，也出现在基础算术、多轮更新和字段抽取。</p>
      <p><b>团队版灵犀与移动灵犀有共同逻辑压力。</b>两者共同失败 {stats["shared_pairs"].get(("团队版灵犀", "移动灵犀"), 0)} 题，明显高于团队版灵犀与豆包的共同失败数。</p>
      <p><b>豆包需要单独关注边界风险。</b>虽然总体错误少，但工具调用边界、禁用词约束和部分学科单选仍有代表性失败。</p>
    </div>
    <div class="panel">
      <h2>失败重叠结构</h2>
      <table>
        <thead><tr><th>失败模式</th><th>题数</th><th>规模</th></tr></thead>
        <tbody>{overlap_html(stats)}</tbody>
      </table>
    </div>
  </section>

  <section class="section">
    <h2>模块数字对比表</h2>
    <div class="panel table-scroll">
      <table class="module-table">
        <thead>
          <tr><th rowspan="2">模块</th><th rowspan="2">并集失败</th>{"".join(f'<th class="group" colspan="2">{esc(product)}</th>' for product in PRODUCTS)}<th rowspan="2">主要观察</th></tr>
          <tr class="subhead">{"".join("<th>错题数</th><th>错率</th>" for _ in PRODUCTS)}</tr>
        </thead>
        <tbody>{module_heatmap_html(payload, stats)}</tbody>
      </table>
    </div>
  </section>

  <section class="section">
    <h2>能力差异归纳</h2>
    <div class="insights">
      <div class="insight"><h3>逻辑推理</h3><p>逻辑推理并集失败 11 题，团队版灵犀和移动灵犀各 7 题，豆包 2 题。团队版灵犀更多出现在必要条件、反事实、自指等核心结论错误；移动灵犀在真假话、排除法、条件链等题型上也不稳定。</p></div>
      <div class="insight"><h3>学科考察</h3><p>学科考察并集失败 12 题，是最集中的失败来源。三者都有错误，说明知识密集型单选题需要从“总体通过率”之外单独评估。</p></div>
      <div class="insight"><h3>指令与边界</h3><p>移动灵犀在格式、字段抽取、多轮更新上有明显样本；豆包在禁用词、澄清问题、工具动作声明上暴露边界问题，风险性质高于普通选项错误。</p></div>
    </div>
  </section>

  <section class="section">
    <h2>代表性案例分析</h2>
    {case_sections}
  </section>

  <section class="section panel appendix">
    <h2>附录与证据</h2>
    <p>全量逐题复核页：<a href="../final-wrong-union-horizontal-review-20260505-v10/final_wrong_union_horizontal_review.html">final_wrong_union_horizontal_review.html</a></p>
    <p>本页只复制代表案例的截图资源，用于解释产品差异；完整截图证据仍以全量报告为准。</p>
  </section>
</main>
</body>
</html>
""")


def main() -> int:
    payload = load_json(OVERVIEW_PATH)
    stats = compute_stats(payload)
    details_by_id = extract_case_details()

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)
    copy_case_assets([item["case_id"] for item in CASE_SELECTION])

    html_text = render_html(payload, stats, details_by_id)
    html_path = OUT_DIR / "final_wrong_union_analysis_report.html"
    html_path.write_text(html_text, encoding="utf-8")

    md_path = OUT_DIR / "final_wrong_union_analysis_report.md"
    md_path.write_text(markdown_report(payload, stats), encoding="utf-8")

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "title": "三产品能力评估分析报告",
        "source_overview": str(OVERVIEW_PATH.resolve()),
        "source_full_report": str(SOURCE_HTML_PATH.resolve()),
        "output_html": str(html_path.resolve()),
        "selected_case_ids": [item["case_id"] for item in CASE_SELECTION],
        "selected_case_count": len(CASE_SELECTION),
        "copied_asset_count": len(list(OUT_ASSET_DIR.glob("*"))),
        "union_count": payload["union_count"],
        "product_summary": payload["product_pass_wrong_summary"],
        "unique_wrong": dict(stats["unique_wrong"]),
        "shared_pairs": {" + ".join(key): value for key, value in stats["shared_pairs"].items()},
    }
    (OUT_DIR / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"HTML {html_path}")
    print(f"MD {md_path}")
    print(f"MANIFEST {OUT_DIR / 'analysis_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
