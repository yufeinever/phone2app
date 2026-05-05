from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "product_eval" / "main-dialogue-300-full-20260504-025041"


WRONG = {
    12: "贝叶斯题实际给出高概率片段，不符合“不一定/概率不高”。",
    13: "拼音排序错误，梨应排在苹果前。",
    21: "时效新闻题直接编造/断言最新新闻，未说明需要联网核验。",
    43: "会话隔离题实际回答用例 ID，未说明无法知道上一会话代号。",
    56: "20字以内约束未满足。",
    59: "未输出 Markdown 表格。",
    73: "量词否定题未作答，反而要求补充背景。",
    110: "政治/时效题给出大量未经核验的当前政策断言。",
    152: "纠错覆盖题未回答最新代号海盐，复述了过程。",
    155: "否定更新题应回答提前，实际说无法确定。",
    156: "列表记忆题应只列第2和第4项，实际列了全部5项。",
    174: "末字约束失败，只有第三句以“安”结尾。",
    178: "双重约束题直接拒绝，未满足关键词和字数约束。",
    181: "Markdown 表格题未生成 Markdown 表格。",
    188: "充分必要题答反；上线可推出通过审核。",
    197: "反事实/逆否题答反；在规则充分时可推出昨天下雨。",
    226: "比例题应为3小时，实际抓取/回答显示为18小时片段。",
    253: "文言翻译期望中文解释，实际给英文翻译。",
    259: "省略歧义题未指出歧义，直接断定小王马上到。",
}

PARTIAL = {
    55: "满足禁词但未解释概念，功能部分缺失。",
    106: "能识别信息不足，但没有按要求提出3个澄清问题。",
    169: "数值正确，但“只输出数字”格式不严格，带 boxed 标记。",
    201: "条件链只推出非A，遗漏非B。",
    262: "金额语义基本对，但不是规范财务大写格式。",
    266: "识别不存在实体，但额外给出疑似过期/错误 Android 最新版本信息。",
    300: "给了合规建议，但对授权自测过度拒绝，安全替代不够好。",
}

CAPTURE = {
    10: "UI/XML 只抓到公式碎片，无法判断是否回答小医院。",
    24: "UI/XML 未抓到模型回答，只抓到题干和首页控件。",
    109: "UI/XML 未抓到模型回答，只抓到题干和首页控件。",
    115: "UI/XML 未抓到模型回答，只抓到题干和首页控件。",
    216: "数学题只抓到公式碎片，无法判断最终答案。",
    217: "数学题只抓到公式碎片，无法判断最终答案。",
    220: "贝叶斯题只抓到公式碎片，无法判断最终答案。",
    228: "增长率题只抓到公式碎片，无法判断最终答案。",
    238: "复杂度题只抓到不完整公式片段，无法确认答案。",
    277: "UI/XML 未抓到模型回答，只抓到题干和首页控件。",
}

TEST_DESIGN = {
    19: "原用例是多轮约束摘要，但本轮只发送了操作摘要，缺少真实5轮上下文。",
    38: "用例要求复述关键词，但未提供具体待复述文本。",
    40: "用例要求超长材料摘要，但未提供1500-3000字材料。",
    41: "用例原本应两轮追问，执行时只发送了操作摘要。",
    42: "用例原本应先给A再改B，执行时只发送了操作摘要。",
    44: "多轮长链路未实际执行5轮补充约束。",
    45: "回答时延已由脚本记录，模型文本本身不能验证该功能点。",
    46: "长回答滚动采集属于UI操作，单轮文本无法验证。",
    47: "复制按钮属于UI操作，单轮文本无法验证剪贴板一致性。",
    48: "朗读按钮属于UI操作，单轮文本无法验证朗读和停止。",
    49: "输入中断恢复属于UI操作，单轮文本无法验证。",
    50: "弱网/断网未实际切换网络，不能验证网络恢复能力。",
    51: "侧栏标题未通过UI操作采集验证。",
    52: "后台切回未实际由该用例步骤验证。",
    57: "只列4条建议但未给建议主题，题干不足。",
    58: "该行只是复用说明，不是可执行题目。",
    60: "A/B/C 题未提供完整题面。",
    75: "三盒标签题缺少完整题设和唯一标准答案。",
    78: "阅读主旨题未提供短文。",
    79: "投诉抽取题未提供投诉文本。",
    80: "表格理解题未提供表格。",
    101: "改写题未提供待改写文本。",
    104: "风格改写题未提供原文。",
    105: "信息抽取题未提供文本。",
    130: "长文本输入题未提供约800字材料。",
    134: "复制回答属于UI/剪贴板动作，单轮文本不能验证。",
    135: "朗读回答属于UI/TTS动作，单轮文本不能验证。",
    136: "生成中断未实际点击停止。",
    137: "页面滚动未实际验证历史可见性。",
    139: "未实际切换弱网或断网。",
    140: "失败消息重试未实际制造失败和点击重试。",
    141: "附件入口未实际进入系统文件选择器再取消。",
    142: "语音静音超时未实际录音等待。",
    143: "键盘/语音切换属于UI操作，单轮文本不能验证。",
    144: "横竖屏切换未由该用例实际操作验证。",
    145: "后台恢复未由该用例实际操作验证。",
    146: "输入草稿保留/清空未由真实切页验证。",
    147: "清空输入框残留未由UI状态验证。",
    148: "首字延迟由脚本指标判断，不由模型回答判断。",
    149: "长回答耗时由脚本指标判断，模型文本不能自证。",
    150: "异常恢复未实际杀后台重启验证。",
    153: "多轮约束保持缺少真实三轮对话内容。",
    154: "指代消解题未提供张三/李四职责上下文。",
    157: "多轮计算缺少具体价格、数量、折扣。",
    158: "话题切换缺少具体旅游需求和代码片段。",
    159: "用户纠正题缺少原错答和纠正条件。",
    161: "长上下文检索未提供长文和隐藏日期。",
    162: "冲突信息处理未提供两个冲突版本。",
    165: "摘要续写未提供会议内容。",
    168: "上下文清理缺少真实代号设置和遗忘步骤。",
    179: "只改错别字未提供待修改文本。",
    190: "该逻辑题按现有题干无满足“恰好两真”的一致解，预期不可靠。",
    200: "该真假话题存在至少两个满足条件的解，预期“甲做了”不唯一。",
    234: "稳定排序题未提供待排序数据。",
    240: "JSON 解析题未提供 JSON 字符串。",
    249: "错别字纠正题未提供待纠正文案。",
    256: "投诉摘要题未提供投诉文本。",
    257: "正式改写题未提供原始口语文本。",
    260: "长文本压缩题未提供1500字材料。",
    263: "简繁转换题未提供繁体句子。",
    264: "专名翻译题未提供待翻译中文句子。",
    276: "最新版本号题未指定软件，题干不足。",
}


def md_cell(value: Any, limit: int = 150) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def verdict_for(index: int) -> tuple[str, str]:
    if index in WRONG:
        return "wrong", WRONG[index]
    if index in PARTIAL:
        return "partial", PARTIAL[index]
    if index in CAPTURE:
        return "capture_issue_rerun", CAPTURE[index]
    if index in TEST_DESIGN:
        return "test_design_issue", TEST_DESIGN[index]
    return "correct", "实际回答满足预期或与预期等价。"


def main() -> int:
    data = json.loads((RUN / "cases.json").read_text(encoding="utf-8"))["results"]
    audited = []
    for index, item in enumerate(data, start=1):
        status, note = verdict_for(index)
        audited.append(
            {
                "index": index,
                "case_id": item["case_id"],
                "module": item.get("module"),
                "feature": item.get("feature"),
                "summary": item.get("summary"),
                "expected": item.get("expected_result"),
                "actual": item.get("actual"),
                "auto_status": item.get("status"),
                "gpt_audit_status": status,
                "gpt_audit_note": note,
                "response_screenshot": item.get("response_screenshot"),
                "first_response_time_ms": item.get("first_response_time_ms"),
                "response_complete_time_ms": item.get("response_complete_time_ms"),
            }
        )

    counts = Counter(row["gpt_audit_status"] for row in audited)
    by_module: dict[str, Counter[str]] = defaultdict(Counter)
    for row in audited:
        by_module[row["module"]][row["gpt_audit_status"]] += 1

    valid = counts["correct"] + counts["wrong"] + counts["partial"]
    lines = [
        "# GPT 人工复核：主对话原 300 题",
        "",
        "## 复核口径",
        "",
        "- `correct`：实际回答满足预期，或与预期逻辑等价。",
        "- `wrong`：实际回答与标准答案或核心要求明确冲突。",
        "- `partial`：核心方向部分正确，但格式、关键点或边界处理不完整。",
        "- `test_design_issue`：用例矩阵只有操作摘要或缺少必要输入材料，不能用本次单轮文本结果判断模型能力。",
        "- `capture_issue_rerun`：UI/XML 抓取未捕获完整回答，需要重跑。",
        "",
        "## 总体结论",
        "",
        "| 状态 | 数量 |",
        "| --- | ---: |",
        f"| correct | {counts.get('correct', 0)} |",
        f"| wrong | {counts.get('wrong', 0)} |",
        f"| partial | {counts.get('partial', 0)} |",
        f"| test_design_issue | {counts.get('test_design_issue', 0)} |",
        f"| capture_issue_rerun | {counts.get('capture_issue_rerun', 0)} |",
        f"| 合计 | {len(audited)} |",
        "",
        f"- 可计分样本：`{valid}`，其中 correct `{counts.get('correct', 0)}`，wrong `{counts.get('wrong', 0)}`，partial `{counts.get('partial', 0)}`。",
        f"- 不计入模型真实对错的样本：`{counts.get('test_design_issue', 0) + counts.get('capture_issue_rerun', 0)}`，包括题干设计不足和抓取问题。",
        "",
        "## 分模块统计",
        "",
        "| 模块 | correct | wrong | partial | test_design_issue | capture_issue_rerun |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for module, counter in by_module.items():
        lines.append(
            f"| {module} | {counter.get('correct', 0)} | {counter.get('wrong', 0)} | "
            f"{counter.get('partial', 0)} | {counter.get('test_design_issue', 0)} | "
            f"{counter.get('capture_issue_rerun', 0)} |"
        )

    lines.extend(
        [
            "",
            "## 错题清单",
            "",
            "| ID | 模块 | 子能力 | 预期 | 实际 | 说明 | 截图 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in audited:
        if row["gpt_audit_status"] == "wrong":
            lines.append(
                f"| {row['case_id']} | {md_cell(row['module'], 40)} | {md_cell(row['feature'], 40)} | "
                f"{md_cell(row['expected'], 90)} | {md_cell(row['actual'], 120)} | "
                f"{md_cell(row['gpt_audit_note'], 120)} | {md_cell(row['response_screenshot'], 70)} |"
            )

    lines.extend(
        [
            "",
            "## 需重跑或修题",
            "",
            "| ID | 状态 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    for row in audited:
        if row["gpt_audit_status"] in {"test_design_issue", "capture_issue_rerun"}:
            lines.append(f"| {row['case_id']} | {row['gpt_audit_status']} | {md_cell(row['gpt_audit_note'], 130)} |")

    lines.extend(
        [
            "",
            "## 全量明细",
            "",
            "| # | ID | 模块 | 子能力 | 自动状态 | GPT复核 | 预期 | 实际摘要 | 说明 |",
            "| ---: | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in audited:
        lines.append(
            f"| {row['index']} | {row['case_id']} | {md_cell(row['module'], 34)} | "
            f"{md_cell(row['feature'], 34)} | {row['auto_status']} | {row['gpt_audit_status']} | "
            f"{md_cell(row['expected'], 90)} | {md_cell(row['actual'], 120)} | {md_cell(row['gpt_audit_note'], 110)} |"
        )

    (RUN / "main300_gpt_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (RUN / "main300_gpt_audit.json").write_text(
        json.dumps(
            {
                "counts": dict(counts),
                "valid_scored_count": valid,
                "by_module": {module: dict(counter) for module, counter in by_module.items()},
                "results": audited,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
