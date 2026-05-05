from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from mobile_lingxi_common import (
    PACKAGE,
    capture_state,
    classify_page,
    dump_xml,
    find_by_id,
    launch_app,
    open_config_menu,
    open_new_chat,
    page_text,
    recover_to_text_chat,
    tap_node,
)


def summarize_controls(nodes) -> list[dict[str, object]]:
    interesting = []
    for node in nodes:
        label = node.text or node.desc or node.resource_id
        if not label:
            continue
        if node.resource_id.startswith(PACKAGE) or node.text or node.desc:
            interesting.append(
                {
                    "class": node.cls,
                    "resource_id": node.resource_id,
                    "text": node.text,
                    "desc": node.desc,
                    "bounds": node.bounds,
                    "clickable": node.clickable,
                }
            )
    return interesting


def write_markdown(run_dir: Path, states: list[dict[str, object]]) -> None:
    lines = [
        "# 移动灵犀重新探测状态模型",
        "",
        f"- 执行时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 包名：`{PACKAGE}`",
        "- 结论：移动灵犀必须按独立状态机处理，不能直接复用旧灵犀的左上侧栏新建会话路径。",
        "",
        "## 状态快照",
        "",
        "| 步骤 | 分类 | 关键可见文本 | 截图 | XML |",
        "| --- | --- | --- | --- | --- |",
    ]
    for state in states:
        visible = str(state.get("visible_text", "")).replace("\n", " / ")
        if len(visible) > 90:
            visible = visible[:90] + "..."
        lines.append(
            f"| {state['name']} | {state['classification']} | {visible} | {state['screenshot']} | {state['xml']} |"
        )

    lines.extend(
        [
            "",
            "## 已确认状态机",
            "",
            "| 状态 | 判定依据 | 恢复/下一步动作 |",
            "| --- | --- | --- |",
            "| `text_chat` | 存在 `com.jiutian.yidonglingxi:id/et_input` | 可输入题干；输入后重新 dump XML 找 `ll_txt_send` |",
            "| `config_menu_open` | 存在 `rl_new_chat` 或同时出现 `自动播报/声音配置/新建对话` | 点 `新建对话` 或按返回关闭菜单 |",
            "| `welcome_personality` | 出现 `想要我怎么称呼你/修改昵称/关闭性格` | 点击底部 `文本` 进入正常聊天页 |",
            "| `voice_input` | 出现 `点击说话` | 点击右下角键盘/文本切换回输入框 |",
            "| `wrong_or_unknown_app` | 前台不含目标包名 | 用 `monkey -p com.jiutian.yidonglingxi ...` 从 Launcher 拉起 |",
            "",
            "## 稳定控件",
            "",
            "| 功能 | selector | 备注 |",
            "| --- | --- | --- |",
            "| 输入框 | `id/et_input` | 每次输入前重新 dump，键盘弹出后位置会变 |",
            "| 发送 | `id/ll_txt_send` | 只在有文本后出现；不能找旧灵犀的 ImageView 发送假设 |",
            "| 右上配置 | `id/img_header_conf` | 新建对话入口在这里，不在左侧栏 |",
            "| 新建对话 | `id/rl_new_chat` / 文本 `新建对话` | 位于右上配置弹层 |",
            "| 语音按钮 | `id/ll_record_voice` | 输入前是语音入口；文本执行时避免误点 |",
        ]
    )
    (run_dir / "state_model.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-state-probe")
    run_dir = Path("reports/mobile_lingxi_probe") / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    states: list[dict[str, object]] = []

    states.append(capture_state(run_dir, "00_initial"))
    launch_app()
    states.append(capture_state(run_dir, "01_after_launcher"))

    recover_to_text_chat(run_dir, "02_recover")
    states.append(capture_state(run_dir, "02_text_chat"))

    menu_nodes = open_config_menu(run_dir, "03")
    states.append(capture_state(run_dir, "03_config_menu"))
    (run_dir / "03_config_menu_controls.json").write_text(
        json.dumps(summarize_controls(menu_nodes), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    new_nodes = open_new_chat(run_dir, "04")
    states.append(capture_state(run_dir, "04_after_new_chat"))

    input_node = find_by_id(new_nodes, ":id/et_input")
    if input_node:
        tap_node(input_node)
    states.append(capture_state(run_dir, "05_input_focused"))

    final_nodes = dump_xml(run_dir / "06_final.xml")
    summary = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "final_classification": classify_page(final_nodes),
        "final_visible_text": page_text(final_nodes),
        "states": states,
    }
    (run_dir / "state_probe.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(run_dir, states)
    print(f"STATE_PROBE_DIR {run_dir}")
    print(f"FINAL_STATE {summary['final_classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
