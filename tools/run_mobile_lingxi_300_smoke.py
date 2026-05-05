from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import run_main_dialogue_eval as runner


MOBILE_PACKAGE = "com.jiutian.yidonglingxi"
MOBILE_ACTIVITY = "com.aspire.jiutian.rebuild.activity.ChatActivity"


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


CASES: list[dict[str, Any]] = [
    {
        "id": "MLX-SMOKE-01",
        "module": "移动灵犀300题冒烟",
        "feature": "单轮严格格式",
        "priority": "P0",
        "precondition": "移动灵犀文本模式，新建对话可用。",
        "steps": ["新建对话", "输入严格 JSON 题", "发送", "记录回答"],
        "turns": [
            {
                "input": "主对话评测 MLX-SMOKE-01：请严格只输出一行 JSON：{\"status\":\"ok\",\"count\":3}。不要解释。",
                "expected": "输出 status=ok 且 count=3。",
                "must_contain": ["status", "ok", "count", "3"],
            }
        ],
    },
    {
        "id": "MLX-SMOKE-02",
        "module": "移动灵犀300题冒烟",
        "feature": "多轮上下文记忆",
        "priority": "P0",
        "precondition": "同一新建对话内连续两轮。",
        "steps": ["记住代号", "追问代号"],
        "turns": [
            {"input": "请记住临时代号“蓝鲸42”，只回答“已记住”。", "expected": "已记住", "must_contain": ["记住"]},
            {"input": "刚才的临时代号是什么？只回答代号。", "expected": "蓝鲸42", "must_contain": ["蓝鲸42"]},
        ],
    },
    {
        "id": "MLX-SMOKE-03",
        "module": "移动灵犀300题冒烟",
        "feature": "上下文更新",
        "priority": "P0",
        "precondition": "同一新建对话内连续三轮。",
        "steps": ["记住旧代号", "更新新代号", "追问当前代号"],
        "turns": [
            {"input": "请记住代号是青竹，只回答已记住。", "expected": "已记住", "must_contain": ["记住"]},
            {"input": "把代号更新为海盐，只回答已更新。", "expected": "已更新", "must_contain": ["更新"]},
            {"input": "当前代号是什么？只回答代号。", "expected": "海盐", "must_contain": ["海盐"], "must_not_contain": ["青竹"]},
        ],
    },
    {
        "id": "MLX-SMOKE-04",
        "module": "移动灵犀300题冒烟",
        "feature": "多轮约束保持",
        "priority": "P0",
        "precondition": "同一新建对话内连续五轮。",
        "steps": ["连续添加约束", "最终汇总"],
        "turns": [
            {"input": "记住任务：为主对话评测写一句结论。只回答已记住。", "expected": "确认记住", "must_contain": ["记住"]},
            {"input": "约束1：语气正式。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "约束2：不超过60字。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "约束3：必须包含“风险”和“建议”。只回答已添加。", "expected": "确认添加", "must_contain": ["添加"]},
            {"input": "现在按所有约束输出最终结论。", "expected": "包含风险和建议", "must_contain": ["风险", "建议"]},
        ],
    },
    {
        "id": "MLX-SMOKE-05",
        "module": "移动灵犀300题冒烟",
        "feature": "长文本提炼",
        "priority": "P1",
        "precondition": "新建对话，中文长文本可输入。",
        "steps": ["输入长材料", "要求提炼5点", "检查关键点"],
        "turns": [
            {
                "input": f"请把下面材料提炼成5点，必须编号1到5：{LONG_AI_MEDICAL}",
                "expected": "输出5点，覆盖风险、责任、灰度等信息。",
                "must_contain": ["1", "2", "3", "4", "5"],
                "any_contain": ["风险", "责任", "灰度", "数据", "医生"],
            }
        ],
    },
    {
        "id": "MLX-SMOKE-06",
        "module": "移动灵犀300题冒烟",
        "feature": "外部硬题-逻辑演绎",
        "priority": "P0",
        "precondition": "新建对话。",
        "steps": ["输入多约束排序选择题", "检查选项输出"],
        "turns": [
            {
                "input": (
                    "Five cars are parked in a row. The truck is newer than the sedan. "
                    "The coupe is older than the van. The sedan is newer than the coupe. "
                    "The convertible is newer than the truck. Which car is the newest? "
                    "A. coupe B. sedan C. truck D. van E. convertible. Answer with the option only."
                ),
                "expected": "E",
                "must_contain": ["E"],
            }
        ],
    },
    {
        "id": "MLX-SMOKE-07",
        "module": "移动灵犀300题冒烟",
        "feature": "外部硬题-状态追踪",
        "priority": "P0",
        "precondition": "新建对话。",
        "steps": ["输入物体交换题", "检查最终持有者"],
        "turns": [
            {
                "input": (
                    "Alice has a red ball, Bob has a blue ball, Claire has a green ball. "
                    "Alice and Bob swap balls. Then Bob and Claire swap balls. "
                    "Who has the red ball now? Answer only the name."
                ),
                "expected": "Claire",
                "must_contain": ["Claire"],
            }
        ],
    },
    {
        "id": "MLX-SMOKE-08",
        "module": "移动灵犀300题冒烟",
        "feature": "外部硬题-符号形式语言",
        "priority": "P0",
        "precondition": "新建对话。",
        "steps": ["输入括号补全题", "检查补全串"],
        "turns": [
            {
                "input": "Complete the bracket sequence so it is balanced: ([{. Output only the missing closing brackets.",
                "expected": "}])",
                "must_contain": ["}", "]", ")"],
                "ordered_contains": ["}", "]", ")"],
            }
        ],
    },
    {
        "id": "MLX-SMOKE-09",
        "module": "移动灵犀300题冒烟",
        "feature": "外部硬题-词序排序",
        "priority": "P0",
        "precondition": "新建对话。",
        "steps": ["输入英文词排序题", "检查顺序"],
        "turns": [
            {
                "input": "Sort these words alphabetically and output only the sorted list: pear, apple, banana, apricot.",
                "expected": "apple, apricot, banana, pear",
                "ordered_contains": ["apple", "apricot", "banana", "pear"],
            }
        ],
    },
]


def mobile_ensure_app() -> None:
    focus = runner.foreground()
    if MOBILE_PACKAGE not in focus:
        runner.adb_text(["shell", "monkey", "-p", MOBILE_PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"], timeout=30)
    runner.time.sleep(1.2)


def mobile_get_version() -> str:
    try:
        out = runner.adb_text(["shell", "dumpsys", "package", MOBILE_PACKAGE], timeout=20)
        version_name = runner.re.search(r"versionName=([^\s]+)", out)
        version_code = runner.re.search(r"versionCode=(\d+)", out)
        return f"{version_name.group(1) if version_name else 'unknown'} ({version_code.group(1) if version_code else 'unknown'})"
    except Exception as exc:
        return f"unknown: {exc}"


def mobile_new_chat(run_dir: Path, prefix: str) -> None:
    # Mobile Lingxi: top-right slider menu -> 新建对话.
    nodes = runner.dump_xml(run_dir / f"{prefix}_new_chat_menu_pre.xml")
    target = next((node for node in nodes if "新建对话" in (node.text or node.desc)), None)
    if not target:
        runner.tap_xy(1018, 162)
        runner.time.sleep(0.45)
        nodes = runner.dump_xml(run_dir / f"{prefix}_new_chat_menu.xml")
        target = next((node for node in nodes if "新建对话" in (node.text or node.desc)), None)
    if target:
        # The text node itself is not clickable; its parent row is around this fixed area.
        runner.tap_xy(860, 526)
    else:
        # If the menu is already dismissed or the page is already fresh, use the known row coordinate as fallback.
        runner.tap_xy(860, 526)
    runner.time.sleep(0.9)
    runner.ensure_text_mode(run_dir, f"{prefix}_new_chat")


def mobile_find_send_button(nodes: Any, edit: Any) -> Any:
    left, top, right, bottom = edit.rect
    candidates = []
    for node in nodes:
        if not node.clickable:
            continue
        n_left, n_top, n_right, n_bottom = node.rect
        if n_left >= 900 and n_top >= top - 20 and n_bottom >= bottom:
            candidates.append(node)
    if not candidates:
        # Fallback to the known Mobile Lingxi send area after text is present.
        class TapProxy:
            @property
            def center(self) -> tuple[int, int]:
                return 984, 2114

        return TapProxy()
    return max(candidates, key=lambda node: (node.rect[2], node.rect[3]))


def mobile_input_text(device: Any, text: str) -> None:
    try:
        device.send_keys(text, clear=True)
    except Exception:
        device.send_keys(text, clear=False)


def mobile_ensure_text_mode(run_dir: Path, prefix: str) -> list[Any]:
    nodes = runner.dump_xml(run_dir / f"{prefix}_text_mode_check.xml")
    if runner.find_edit(nodes):
        return nodes
    text = runner.page_text(nodes)
    if "想要我怎么称呼你" in text or "修改昵称" in text:
        # Mobile Lingxi sometimes lands on a welcome/personality page after 新建对话.
        # The bottom-right "文本" button enters the normal chat composer.
        runner.tap_xy(725, 1976)
        runner.time.sleep(1.0)
        nodes = runner.dump_xml(run_dir / f"{prefix}_text_mode_after_welcome_text.xml")
        if runner.find_edit(nodes):
            return nodes
    if "点击说话" in text:
        runner.tap_xy(984, 2114)
        runner.time.sleep(0.8)
        nodes = runner.dump_xml(run_dir / f"{prefix}_text_mode_after_voice_toggle.xml")
    return nodes


def patch_runner_for_mobile() -> None:
    runner.PACKAGE = MOBILE_PACKAGE
    runner.ACTIVITY = MOBILE_ACTIVITY
    runner.ensure_app = mobile_ensure_app
    runner.get_version = mobile_get_version
    runner.new_chat = mobile_new_chat
    runner.find_send_button = mobile_find_send_button
    runner.ensure_text_mode = mobile_ensure_text_mode
    runner.input_text = mobile_input_text


def main() -> int:
    patch_runner_for_mobile()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-mobile-lingxi-300-smoke")
    run_dir = Path("reports/mobile_lingxi_eval") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    start = datetime.now()
    runner.ensure_app()
    device = runner.set_fast_input()
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "start_time": start.isoformat(timespec="seconds"),
        "execution_mode": "移动灵犀300题执行冒烟：覆盖单轮、多轮、长文本、外部硬题",
        "device": runner.adb_text(["devices", "-l"], timeout=10).strip(),
        "app": f"{MOBILE_PACKAGE}/{MOBILE_ACTIVITY}",
        "app_version": runner.get_version(),
        "network": "当前真机网络，未单独切换弱网",
    }
    results: list[dict[str, Any]] = []
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
        runner.time.sleep(0.5)
    metadata["end_time"] = datetime.now().isoformat(timespec="seconds")
    runner.write_summary(run_dir, metadata, results)
    notes = [
        "# 移动灵犀 300题执行冒烟说明",
        "",
        "本批次不是正式300题结果，只验证移动灵犀是否能稳定执行统一题库所需的关键路径。",
        "",
        "覆盖类型：",
        "",
        "- 单轮严格格式",
        "- 多轮上下文记忆",
        "- 上下文更新",
        "- 多轮约束保持",
        "- 长文本提炼",
        "- 外部硬题：逻辑演绎、状态追踪、符号形式语言、词序排序",
        "",
        "移动灵犀新建对话路径：右上角滑杆菜单 -> 新建对话。",
    ]
    (run_dir / "smoke_notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")
    print(f"RESULT_DIR {run_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
