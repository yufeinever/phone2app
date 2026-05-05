# phone2app

Android 真机 App 性能与时延分析框架。第一版面向“仅 APK + 测试账号”的黑盒/灰盒场景，通过 USB 连接真机，自动执行配置化业务流程，采集启动、交互、渲染、CPU、内存、网络流量、logcat、Crash/ANR 和可选 Perfetto trace，输出 JSON 与 Markdown 报告。

## 环境要求

- Windows + PowerShell
- Python 3.9+（推荐 3.11+）
- Android SDK Platform Tools，确保 `adb` 在 `PATH` 中
- Android 真机开启开发者选项和 USB debugging
- 可选：Node.js + Appium 2 + UiAutomator2 driver

依赖安装：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

如果国内源不可用，可按环境规则使用本地代理 `127.0.0.1:10808`。

Appium 可选安装：

```powershell
.\scripts\setup_appium.ps1
```

复杂组件交互推荐使用 Appium + UiAutomator2：

```powershell
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
appium --address 127.0.0.1 --port 4723
```

中文输入推荐使用 `uiautomator2` 的 FastInputIME 能力，作为 Appium 的输入补充。

真机 Appium E2E 用例默认跳过。确认 Appium server 和手机连接正常后运行：

```powershell
$env:PHONE2APP_APPIUM_E2E='1'
python -m pytest tests\e2e -q
```

## 快速开始

1. 编辑 [configs/scenarios.yaml](configs/scenarios.yaml)，填入目标 App 的 `package`、`activity` 和场景步骤。
2. 手机 USB 连接电脑并授权调试。
3. 运行环境检查：

```powershell
python -m phone2app doctor --device-config configs/devices.yaml --scenario-config configs/scenarios.yaml
```

4. 执行采集：

```powershell
python -m phone2app run --device-config configs/devices.yaml --scenario-config configs/scenarios.yaml --output reports
```

5. 对比基线：

```powershell
python -m phone2app compare --current reports\latest\report.json --baseline reports\baseline\report.json
```

## 场景能力

当前内置动作：

- `launch`：通过 `adb shell am start -W` 启动 Activity，并采集启动耗时。
- `wait`：等待固定秒数。
- `tap_text` / `tap_text_contains`：通过 `uiautomator dump` 找文本并用 `adb input tap` 点击。
- `tap_content_desc` / `tap_content_desc_contains` / `tap_accessibility_id`：通过 content-desc 点击。
- `tap_resource_id`：通过 resource-id 点击。
- `tap_xy`：按坐标点击。
- `assert_text` / `assert_text_contains` / `assert_content_desc` / `assert_content_desc_contains`：断言文本或 content-desc 可见。
- `input_text`：通过 `adb input text` 输入文本。
- `press_back`：通过 adb 返回。
- `tap_xpath`：通过 Appium 点击 XPath。

只有包含 `tap_xpath` 等 adb 无法原生支持的动作时才需要启动 Appium server。常见文本点击、坐标点击、断言和返回只依赖 `adb`。

## 复杂组件框架

项目新增了 `phone2app.appium_ext`，用于后续系统化测试：

- `ChatPage`：普通对话页、输入框、发送按钮、语音输入、附件入口。
- `FeatureCarousel`：底部横向功能栏，支持左右滑动、按功能名点击。
- `AttachmentSheet`：`+` 面板，支持图片/文件/取消。
- `SystemFilePickerPage`：Android 系统文件选择器。
- `AvCallPage`：AI 音视频通话页，支持字幕和退出。
- `FastInputImeProvider`：中文、长文本、多行文本输入 Provider。

配置文件位于 [configs/appium.yaml](configs/appium.yaml)。

## LLM 主对话评测资产

仓库包含当前三款 App 横向评测所需的核心脚本和用例集，但不包含历史执行报告、截图、XML、trace 和人工复核 HTML。

可执行用例集位于：

- `data/eval_cases/main-dialogue-300-v3.2/cases.json`：300 题完整池，其中 274 题为纯文本主对话题，26 题为产品操作/性能采集题。
- `data/eval_cases/main-dialogue-300-v3.2/dialogue_cases.json`：274 题主对话模型题。
- `data/eval_cases/main-dialogue-300-v3.2/operation_cases.json`：26 题产品操作题。
- `data/eval_cases/ceval-abcd-50/cases.json`：50 题 C-Eval 单选学科考察题。

产品专用 runner 位于 `tools/`：

- `run_main_dialogue_eval.py`：团队版灵犀主对话 runner。
- `run_mobile_lingxi_eval.py` / `mobile_lingxi_common.py`：移动灵犀 runner 与状态机。
- `run_doubao_eval.py` / `doubao_common.py`：豆包 runner 与状态机。
- `run_rotating_main_dialogue_eval.py`：三产品轮转执行调度器。
- `judge_main_dialogue_cross_eval.py`：赛后横向裁判。

真机序列号不写死在公开配置中。多设备场景下先设置：

```powershell
$env:ANDROID_SERIAL='<your-adb-serial>'
```

裁判模型密钥通过环境变量注入，不写入仓库：

```powershell
$env:JUDGE_API_KEY='<your-key>'
```

## 输出

每次运行会生成独立目录：

- `report.json`：机器可读原始数据和汇总指标。
- `report.md`：人工阅读报告。
- `logcat/*.log`：每次迭代 logcat。
- `traces/*.perfetto-trace`：可选 Perfetto trace。

## 指标说明

- 启动：`ThisTime`、`TotalTime`、`WaitTime`。
- 交互：每个场景迭代 wall time，输出 P50/P90/P95。
- 渲染：`dumpsys gfxinfo` 的总帧数、janky frames、percentile。
- 资源：CPU 快照、PSS 内存、网络字节差分、电量统计快照。
- 稳定性：logcat 中 `FATAL EXCEPTION`、`ANR in`、`Application Not Responding` 等事件。

## 阈值

默认阈值位于 [configs/thresholds.yaml](configs/thresholds.yaml)。`compare` 会按阈值给出 `pass`、`warn`、`fail`。
