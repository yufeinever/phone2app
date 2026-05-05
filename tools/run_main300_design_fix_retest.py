from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import run_main_dialogue_eval as runner


LONG_AI_MEDICAL = (
    "某医院准备上线一套 AI 辅助阅片系统，用于肺结节筛查、糖尿病视网膜病变识别和急诊影像初筛。"
    "项目目标是缩短医生阅片时间，提高早期病灶发现率，并让基层医生获得更稳定的辅助判断。"
    "试点阶段发现，系统在标准清晰影像上准确率较高，但在低质量影像、罕见病变和儿童病例上表现波动。"
    "数据治理团队指出，训练样本主要来自东部大型医院，西部地区、老年患者和少数民族样本比例不足。"
    "法务部门担心，一旦 AI 给出错误提示，责任在医院、医生还是供应商之间难以界定。"
    "信息安全团队发现，部分测试数据脱敏不充分，仍可能通过时间、科室、住院号组合反推出患者身份。"
    "医生代表认为，AI 可以作为第二意见，但不能替代医生签字；护士团队希望系统提示更加简洁，避免增加工作负担。"
    "产品团队计划先在三家医院灰度上线三个月，期间记录误报率、漏报率、医生采纳率、平均阅片耗时和患者投诉。"
    "上线前还需要完成伦理审查、患者告知、日志审计、模型版本回滚和异常工单处理机制。"
)

MEETING = (
    "5月8日项目例会决定：第一，性能专项由王敏负责，5月15日前完成启动时延和首字响应时延基线；"
    "第二，语音专项由赵磊负责，5月18日前完成静音、弱网和嘈杂环境三组测试；"
    "第三，安全专项由陈宁负责，5月20日前整理提示词注入和隐私诱导用例。"
    "会议还要求各负责人每天18点前更新风险，遇到阻塞当天升级给项目经理。"
)

COMPLAINT = (
    "用户投诉：我昨天晚上8点在灵犀里上传了一份20MB的合同附件，页面一直转圈，最后提示失败。"
    "我切换网络后重试两次仍然失败，客服只让我重新登录，没有解释原因。"
    "我希望你们查明失败原因，补偿我因此耽误的时间，并给出明确的修复时间。"
    "证据包括失败截图、上传时间记录和客服聊天记录。"
)

TABLE = "产品,本周请求数,失败数\n主对话,1200,18\n语音通话,360,27\n文件上传,240,36"

LONG_DELIVERY = (
    "项目背景：灵犀主对话评测需要覆盖输入、上下文、时延和安全四条主线。"
    "第一阶段完成设备连接、文本输入和截图采集。第二阶段补齐多轮对话、长文本和复制朗读。"
    "风险包括网络不稳定、UI 控件变动、日志抓取不完整和部分题目缺少标准答案。"
    "负责人要求所有报告保留 summary、case_overview、cases.json、截图和 XML。"
    "隐藏信息：本轮最终交付日期是 2026-05-12。"
    "后续安排包括修复题库、重跑缺陷用例、人工审核错题并形成版本基线。"
)


CASES: list[dict[str, Any]] = [
    {
        "id": "FIX-MD-X19",
        "module": "设计问题修复",
        "feature": "多轮约束保持",
        "priority": "P0",
        "precondition": "真实多轮会话。",
        "steps": ["连续添加约束", "最终汇总"],
        "turns": [
            {"input": "记住任务：为主对话评测写一句结论。只回答已记住。", "expected": "确认记住", "must_contain": ["记住"]},
            {"input": "约束1：语气正式。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "约束2：不超过60字。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "约束3：必须包含“风险”和“建议”。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "现在按所有约束输出最终结论。", "expected": "包含风险和建议，语气正式", "must_contain": ["风险", "建议"]},
        ],
    },
    {
        "id": "FIX-MD-F02",
        "module": "设计问题修复",
        "feature": "中英混输",
        "priority": "P1",
        "precondition": "补齐具体文本。",
        "steps": ["输入混合文本", "复述关键词"],
        "turns": [
            {
                "input": "请复述这句话里的关键词：灵犀App v1.10.16 在 Android 10 上测试，指标包括 P90、Crash、ANR；只列关键词。",
                "expected": "保留灵犀App、v1.10.16、Android 10、P90、Crash、ANR",
                "must_contain": ["灵犀", "v1.10.16", "Android", "10", "P90", "Crash", "ANR"],
            }
        ],
    },
    {
        "id": "FIX-MD-F04",
        "module": "设计问题修复",
        "feature": "长文本提炼",
        "priority": "P1",
        "precondition": "补齐长文本材料。",
        "steps": ["输入材料", "提炼5点"],
        "turns": [
            {
                "input": f"请把下面材料提炼成5点，必须编号1到5：{LONG_AI_MEDICAL}",
                "expected": "输出5点，覆盖目标、风险、治理、责任、灰度指标",
                "must_contain": ["1", "2", "3", "4", "5"],
                "any_contain": ["风险", "责任", "灰度", "数据", "医生"],
            }
        ],
    },
    {
        "id": "FIX-MD-F05",
        "module": "设计问题修复",
        "feature": "多轮上下文",
        "priority": "P0",
        "precondition": "真实两轮。",
        "steps": ["记住代号", "追问代号"],
        "turns": [
            {"input": "请记住临时代号“蓝鲸42”，只回答“已记住”。", "expected": "已记住", "must_contain": ["已记住"]},
            {"input": "刚才的临时代号是什么？只回答代号。", "expected": "蓝鲸42", "must_contain": ["蓝鲸42"]},
        ],
    },
    {
        "id": "FIX-MD-F06",
        "module": "设计问题修复",
        "feature": "上下文更新",
        "priority": "P0",
        "precondition": "真实三轮。",
        "steps": ["记住A", "更新B", "追问"],
        "turns": [
            {"input": "请记住代号是青竹，只回答已记住。", "expected": "已记住", "must_contain": ["记住"]},
            {"input": "把代号更新为海盐，只回答已更新。", "expected": "已更新", "must_contain": ["更新"]},
            {"input": "当前代号是什么？只回答代号。", "expected": "海盐", "must_contain": ["海盐"], "must_not_contain": ["青竹"]},
        ],
    },
    {
        "id": "FIX-MD-I05",
        "module": "设计问题修复",
        "feature": "列表数量",
        "priority": "P1",
        "precondition": "补齐建议主题。",
        "steps": ["只列4条建议"],
        "turns": [
            {
                "input": "请只列4条提升移动App启动速度的建议，不要解释。",
                "expected": "正好4条建议",
                "must_contain": ["1", "2", "3", "4"],
            }
        ],
    },
    {
        "id": "FIX-MD-I08",
        "module": "设计问题修复",
        "feature": "只回答选项",
        "priority": "P1",
        "precondition": "补齐选择题。",
        "steps": ["选择A/B/C"],
        "turns": [
            {"input": "只回答选项：水在标准大气压下通常多少摄氏度沸腾？A. 50 B. 100 C. 200", "expected": "B", "must_contain": ["B"]},
        ],
    },
    {
        "id": "FIX-MD-R10",
        "module": "设计问题修复",
        "feature": "阅读主旨",
        "priority": "P1",
        "precondition": "补齐短文。",
        "steps": ["阅读短文", "回答主旨"],
        "turns": [
            {
                "input": "阅读短文并概括主旨：很多团队在上线前只关注功能是否可用，却忽视时延、失败恢复和安全边界。成熟评测应把性能、稳定性和安全纳入日常回归。请用一句话回答主旨。",
                "expected": "主旨是评测应覆盖性能、稳定性、安全，而不只功能",
                "any_contain": ["性能", "稳定", "安全", "回归", "功能"],
            }
        ],
    },
    {
        "id": "FIX-MD-R11",
        "module": "设计问题修复",
        "feature": "观点抽取",
        "priority": "P1",
        "precondition": "补齐投诉文本。",
        "steps": ["抽取诉求和情绪"],
        "turns": [
            {
                "input": f"从下面投诉中抽取“诉求”和“情绪”，用两行回答：{COMPLAINT}",
                "expected": "诉求包含查明原因、补偿、修复时间；情绪是不满/焦急",
                "must_contain": ["诉求", "情绪"],
                "any_contain": ["补偿", "修复", "不满", "焦急", "失败原因"],
            }
        ],
    },
    {
        "id": "FIX-MD-R12",
        "module": "设计问题修复",
        "feature": "表格理解",
        "priority": "P1",
        "precondition": "补齐表格。",
        "steps": ["读取表格", "计算最大失败率"],
        "turns": [
            {
                "input": f"表格如下：\n{TABLE}\n哪个产品失败率最高？请给出产品名和失败率。",
                "expected": "文件上传失败率最高，36/240=15%",
                "must_contain": ["文件上传"],
                "any_contain": ["15%", "0.15", "15"],
            }
        ],
    },
    {
        "id": "FIX-MD-W03",
        "module": "设计问题修复",
        "feature": "商务改写",
        "priority": "P1",
        "precondition": "补齐原文。",
        "steps": ["改写语气"],
        "turns": [
            {
                "input": "把这句话从抱怨语气改成商务沟通语气，不改变事实：你们这个接口又慢又不稳定，昨天害我们测试全卡住了。",
                "expected": "语气专业且保留接口慢、不稳定、测试受阻",
                "any_contain": ["接口", "不稳定", "测试", "影响", "优化"],
            }
        ],
    },
    {
        "id": "FIX-MD-W07",
        "module": "设计问题修复",
        "feature": "信息抽取",
        "priority": "P1",
        "precondition": "补齐文本。",
        "steps": ["抽取字段"],
        "turns": [
            {
                "input": "从文本抽取时间、地点、人物、事项：5月12日14点，王敏在北京研发中心三楼会议室组织主对话评测复盘会。",
                "expected": "时间5月12日14点，地点北京研发中心三楼会议室，人物王敏，事项主对话评测复盘会",
                "must_contain": ["5月12日", "14点", "王敏", "北京研发中心", "评测复盘"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-F02",
        "module": "设计问题修复",
        "feature": "800字摘要",
        "priority": "P1",
        "precondition": "补齐材料。",
        "steps": ["输入材料", "三点摘要"],
        "turns": [
            {
                "input": f"请把下面材料压缩为三点摘要，每点不超过35字：{LONG_AI_MEDICAL}",
                "expected": "三点摘要，覆盖目标、风险和治理",
                "must_contain": ["1", "2", "3"],
                "any_contain": ["风险", "数据", "医生", "灰度", "责任"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-C03",
        "module": "设计问题修复",
        "feature": "多约束保持",
        "priority": "P1",
        "precondition": "真实三轮约束。",
        "steps": ["添加约束", "汇总"],
        "turns": [
            {"input": "之后回答请使用正式语气。只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "再加约束：最终回答不超过50字。只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "再加约束：最终回答必须包含“结论”和“建议”。只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "请按以上全部约束，总结主对话评测需要补齐可执行题干。", "expected": "包含结论和建议", "must_contain": ["结论", "建议"]},
        ],
    },
    {
        "id": "FIX-MD-EX-C04",
        "module": "设计问题修复",
        "feature": "指代消解",
        "priority": "P1",
        "precondition": "补齐人物职责。",
        "steps": ["介绍人物", "追问指代"],
        "turns": [
            {"input": "张三负责性能测试，李四负责安全测试。请只回答已知。", "expected": "已知", "must_contain": ["已知"]},
            {"input": "他负责安全测试吗？这里的他指李四。只回答是或否。", "expected": "是", "must_contain": ["是"]},
        ],
    },
    {
        "id": "FIX-MD-EX-C07",
        "module": "设计问题修复",
        "feature": "多轮计算",
        "priority": "P1",
        "precondition": "真实三轮信息。",
        "steps": ["价格数量", "折扣", "计算"],
        "turns": [
            {"input": "商品单价80元，购买3件。只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "现在打九折。只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "总价是多少？只输出数字和元。", "expected": "216元", "must_contain": ["216"]},
        ],
    },
    {
        "id": "FIX-MD-EX-C08",
        "module": "设计问题修复",
        "feature": "话题切换",
        "priority": "P2",
        "precondition": "真实话题切换。",
        "steps": ["旅游", "代码", "回旅游"],
        "turns": [
            {"input": "我计划周末去杭州两天，预算1000元。请只回答已记录。", "expected": "已记录", "must_contain": ["记录"]},
            {"input": "解释代码：return x * x。只用一句话。", "expected": "平方", "any_contain": ["平方", "乘以自身"]},
            {"input": "回到刚才旅游话题，我的目的地和预算是什么？", "expected": "杭州，两天，1000元", "must_contain": ["杭州", "1000"]},
        ],
    },
    {
        "id": "FIX-MD-EX-C11",
        "module": "设计问题修复",
        "feature": "长上下文检索",
        "priority": "P1",
        "precondition": "补齐长文。",
        "steps": ["输入长文", "抽取日期"],
        "turns": [
            {"input": f"阅读材料并记住关键信息：{LONG_DELIVERY}。只回答已阅读。", "expected": "已阅读", "must_contain": ["阅读"]},
            {"input": "本轮最终交付日期是什么？只回答日期。", "expected": "2026-05-12", "must_contain": ["2026-05-12"]},
        ],
    },
    {
        "id": "FIX-MD-EX-C12",
        "module": "设计问题修复",
        "feature": "冲突信息处理",
        "priority": "P1",
        "precondition": "补齐冲突版本。",
        "steps": ["提供冲突事实", "判断"],
        "turns": [
            {
                "input": "资料A说上线日期是5月10日；资料B说上线日期是5月18日。无法确认哪个来源更权威。请判断上线日期。",
                "expected": "指出冲突且无法唯一确定",
                "must_contain": ["冲突"],
                "any_contain": ["无法确定", "不能确定", "无法唯一"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-C15",
        "module": "设计问题修复",
        "feature": "摘要续写",
        "priority": "P1",
        "precondition": "补齐会议内容。",
        "steps": ["摘要", "待办"],
        "turns": [
            {
                "input": f"先摘要会议，再根据摘要写待办，分两段输出：{MEETING}",
                "expected": "待办与负责人和时间一致",
                "must_contain": ["王敏", "赵磊", "陈宁"],
                "any_contain": ["5月15", "5月18", "5月20"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-C18",
        "module": "设计问题修复",
        "feature": "上下文清理",
        "priority": "P1",
        "precondition": "真实设置后遗忘。",
        "steps": ["设置代号", "要求忘记", "追问"],
        "turns": [
            {"input": "请记住代号是松石。只回答已记住。", "expected": "已记住", "must_contain": ["记住"]},
            {"input": "请忘掉刚才的代号。只回答已忘掉。", "expected": "已忘掉", "must_contain": ["忘"]},
            {"input": "刚才的代号是什么？", "expected": "不应回答松石", "must_not_contain": ["松石"]},
        ],
    },
    {
        "id": "FIX-MD-EX-I11",
        "module": "设计问题修复",
        "feature": "只改错别字",
        "priority": "P1",
        "precondition": "补齐原文。",
        "steps": ["只改错别字"],
        "turns": [
            {
                "input": "只改错别字，不润色：明天我们在会义室讨伦测试方按。",
                "expected": "明天我们在会议室讨论测试方案",
                "must_contain": ["会议室", "讨论", "方案"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-L04",
        "module": "设计问题修复",
        "feature": "排除法唯一解",
        "priority": "P1",
        "precondition": "重写为有唯一解。",
        "steps": ["解唯一真假题"],
        "turns": [
            {
                "input": "甲乙丙三人中只有一人说真话。甲说：乙做了。乙说：我没有做。丙说：乙没有做。已知只有一人做了，谁做了？",
                "expected": "乙做了",
                "must_contain": ["乙"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-P04",
        "module": "设计问题修复",
        "feature": "稳定排序",
        "priority": "P1",
        "precondition": "补齐数据。",
        "steps": ["稳定排序"],
        "turns": [
            {
                "input": "按分数降序排序，分数相同保持原顺序：A=90，B=95，C=90，D=95。只输出姓名顺序。",
                "expected": "B、D、A、C",
                "ordered_contains": ["B", "D", "A", "C"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-P10",
        "module": "设计问题修复",
        "feature": "JSON解析",
        "priority": "P1",
        "precondition": "补齐JSON。",
        "steps": ["解析缺失字段"],
        "turns": [
            {
                "input": "解析JSON并输出name、age、city，缺失填null：{\"name\":\"Lin\",\"city\":\"Shanghai\"}",
                "expected": "name Lin, age null, city Shanghai",
                "must_contain": ["Lin", "null", "Shanghai"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z01",
        "module": "设计问题修复",
        "feature": "错别字纠正",
        "priority": "P1",
        "precondition": "补齐文本。",
        "steps": ["纠错"],
        "turns": [
            {
                "input": "把这句话改为无错别字版本：请各位同事准时参加会义，并提前阅读测试方按。",
                "expected": "会议，方案",
                "must_contain": ["会议", "方案"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z08",
        "module": "设计问题修复",
        "feature": "投诉摘要",
        "priority": "P1",
        "precondition": "补齐投诉文本。",
        "steps": ["原因诉求证据"],
        "turns": [
            {
                "input": f"把投诉内容摘要成原因、诉求、证据三项：{COMPLAINT}",
                "expected": "原因上传失败，诉求查明补偿修复，证据截图记录客服聊天",
                "must_contain": ["原因", "诉求", "证据"],
                "any_contain": ["失败", "补偿", "截图", "客服"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z09",
        "module": "设计问题修复",
        "feature": "正式改写",
        "priority": "P1",
        "precondition": "补齐原文。",
        "steps": ["正式公告语气"],
        "turns": [
            {
                "input": "把这句话改成正式公告语气：大家注意，明天早上别迟到，系统要升级，晚了就测不了了。",
                "expected": "正式，包含明早、系统升级、准时",
                "any_contain": ["明天", "系统升级", "准时", "测试"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z12",
        "module": "设计问题修复",
        "feature": "长文本压缩",
        "priority": "P1",
        "precondition": "补齐长文本。",
        "steps": ["压缩到200字内"],
        "turns": [
            {
                "input": f"将下面材料压缩到200字内：{LONG_AI_MEDICAL}",
                "expected": "200字内且保留重点",
                "any_contain": ["AI", "风险", "医生", "数据", "灰度"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z15",
        "module": "设计问题修复",
        "feature": "简繁转换",
        "priority": "P1",
        "precondition": "补齐繁体。",
        "steps": ["繁转简"],
        "turns": [
            {
                "input": "把繁体转成简体：請確認語音輸入功能是否正常，並記錄測試結果。",
                "expected": "请确认语音输入功能是否正常，并记录测试结果",
                "must_contain": ["请确认", "语音输入", "测试结果"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-Z16",
        "module": "设计问题修复",
        "feature": "专名翻译",
        "priority": "P1",
        "precondition": "补齐中文句子。",
        "steps": ["翻译保留专名"],
        "turns": [
            {
                "input": "翻译成英文并保留专名：我们使用 OpenAI、Android 和 Perfetto 分析主对话性能。",
                "expected": "保留 OpenAI Android Perfetto",
                "must_contain": ["OpenAI", "Android", "Perfetto"],
            }
        ],
    },
    {
        "id": "FIX-MD-EX-T12",
        "module": "设计问题修复",
        "feature": "过期知识",
        "priority": "P1",
        "precondition": "指定软件。",
        "steps": ["最新版本边界"],
        "turns": [
            {
                "input": "请绝对准确告诉我 Chrome 当前最新稳定版版本号。如果不能实时联网核验，请说明不能保证。",
                "expected": "说明需要实时查询或不能保证",
                "any_contain": ["实时", "联网", "无法保证", "不能保证", "查询"],
            }
        ],
    },
]


def main() -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-main300-design-fix")
    run_dir = Path("reports/product_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now()
    runner.ensure_app()
    device = runner.set_fast_input()
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "start_time": start.isoformat(timespec="seconds"),
        "execution_mode": "设计问题修复重测：补材料 + 真实多轮 + adb/uiautomator2",
        "device": runner.adb_text(["devices", "-l"], timeout=10).strip(),
        "app": f"{runner.PACKAGE}/{runner.ACTIVITY}",
        "app_version": runner.get_version(),
        "network": "当前真机网络，未单独切换弱网",
    }
    results = []
    progress = run_dir / "progress.log"
    for index, case in enumerate(CASES, start=1):
        msg = f"{datetime.now().isoformat(timespec='seconds')} RUN {index}/{len(CASES)} {case['id']} {case['feature']}"
        print(msg, flush=True)
        progress.open("a", encoding="utf-8").write(msg + "\n")
        result = runner.run_case(run_dir, device, case)
        results.append(result)
        done = f"{datetime.now().isoformat(timespec='seconds')} DONE {index}/{len(CASES)} {case['id']} status={result['status']} duration_ms={result['duration_ms']}"
        print(done, flush=True)
        progress.open("a", encoding="utf-8").write(done + "\n")
        metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
        runner.write_summary(run_dir, metadata, results)
    metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
    runner.write_summary(run_dir, metadata, results)

    notes = [
        "# 设计问题处理说明",
        "",
        "本批次只重测可通过补材料或真实多轮执行修复的用例。",
        "",
        "未纳入本批次的原 test_design_issue 主要是 UI/设备操作类，例如复制、朗读、弱网、后台恢复、附件入口、语音静音、横竖屏等；这些应进入产品功能自动化，而不是模型问答评分。",
        "",
        "另有复用说明类用例应退役，例如原 `MD-I06`。",
        "",
    ]
    (run_dir / "design_issue_resolution.md").write_text("\n".join(notes), encoding="utf-8")
    print(f"RESULT_DIR {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
