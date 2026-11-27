
# ComicFlow Validator

**A Local-First Desktop Tool for AI Comic Production**

一款面向 AI 漫剧创作者的本地素材验收工具。

[English](#english) | [简体中文](#简体中文)

---

## English

### Overview

ComicFlow Validator is an open-source desktop tool designed to help AI comic creators validate production assets and delivery packages.

The goal is to reduce repetitive manual checks and improve the reliability of production workflows.

### Current Checks

- Image integrity and dimension checks
- Aspect ratio validation
- ZIP entry and CRC checks, with a SHA-256 digest from the archive checker
- Directory and ZIP delivery reports with optional JSON rules for required files, directories, and extensions
- Complete storyboard package validation through the installed workflow's validator

### Design Principles

- Local-first: Files remain on the user's computer.
- Read-only: Original production assets are not modified.
- Transparent: Every validation result should have a clear reason.
- Accessible: Designed for independent creators and small teams.

### Current Status

Version: 0.1.0

**Early development.**

Storyboard validation is available from the command line and a Windows launcher.

### Run from Source

Requirements: Python 3.13 (tested).

```bash
python -m pip install -r requirements.txt
python -m src.image_checker "path/to/images" --ratio 16:9
python -m src.delivery_checker "path/to/delivery.zip"
python -m pytest -q
```

For a complete storyboard package, provide the final ZIP and the trusted `scripts/validate_storyboard_package.py` from your installed storyboard workflow. ComicFlow checks the ZIP and unpacks it temporarily for storyboard validation.

```bash
python -m src.delivery_checker "path/to/delivery.zip" --storyboard-validator "path/to/workflow/scripts/validate_storyboard_package.py"
```

When you also have an independently validated delivery folder, provide both paths to compare its files with the final ZIP by SHA-256.

```bash
python -m src.delivery_checker "path/to/delivery" --storyboard-validator "path/to/workflow/scripts/validate_storyboard_package.py" --zip "path/to/delivery.zip"
```

Strict mode is the default. Use `--allow-legacy` for historical packages. `--rules` can add project-specific preflight rules to the delivery directory. Visual identity, actual camera geometry, readability, action continuity, and video still require review.

When reviewing a package from another workspace, add `--review-missing-sources` to report inaccessible local reuse sources as unverified. Exit code `3` means that source availability was the only outstanding check. Exit code `1` still indicates errors such as missing deliverables, mismatched file bytes, or invalid panel counts. Code `0` indicates that the automated checks ran without errors.

On Windows, install the requirements for Python 3 with Tcl/Tk. The launcher prefers the project's `.venv`, then tries `python` and `py -3` for an interpreter with its desktop dependencies. Double-click `ComicFlow-Windows.bat` and pick a ZIP, or drop a ZIP on the `.bat` file in Explorer. Select the trusted workflow validator, then start the check. Set `COMICFLOW_STORYBOARD_VALIDATOR` to prefill its path. The result table shows groups, shot IDs and filenames when the validator identifies them. Select a row to preview its text or image in the window, or switch to the full report tab.

For an approved extra-panel exception to the six-panel dialogue rule, pass `--panel-exception file.json` when validating a ZIP directly, or select the JSON in the launcher. The entry is tied to one ZIP SHA-256, one group such as `SB05`, its approved `panels` count (7–12), and a one-line `reason`. Only the matching six-panel-rule diagnostic is treated as an approved exception.

For optional AI review, preview a PNG, JPEG or WebP and click 「AI 辅助看图」. The menu offers 12 provider presets and custom OpenAI-compatible Chat Completions. Enter the vision model ID and API key. The HTTPS base address is configurable. The selected image and a review prompt are sent after confirmation. Images over 6 MiB are prepared as a compressed local copy before sending. Credentials stay in memory for the current session. AI suggestions stay separate from the local validation result.

Use 「生图前预检」 to count planned files against the nine-image upload limit. For dialogue, import or paste the approved sentence JSON and choose 「预排完整句」. This runs `plan_english_dialogue.py` beside the selected workflow validator and shows candidate groups, word counts, and original dialogue IDs and spans. Candidate groups still need review against shot continuity before production. Both checks run locally.

After checking a complete ZIP, use 「逐格复核」 to select a shot and compare its storyboard sheet, referenced clean plate and slot, production record, and SD2 prompt. The window shows neighboring storyboard thumbnails and action summaries and can step between groups. Drag over either image to zoom into the selected pane. Manual regions are kept per shot until the review window closes. Review is read-only and local.

Use 「资产与返修」 to create or select a local asset database. Register approved originals by asset ID and version. A scan of a new directory can relink a renamed or moved file by exact SHA-256. New production records can use `asset:ID@version` in the reuse ledger. For old records, register the source path printed in the ledger as the original reference. The selected database is used in the workbench validator, or pass `--asset-registry` on the CLI.

In 「返修打包」, enter a shot ID to see related files in the most recently checked ZIP. Select the repaired delivery directory, workflow validator, and a new ZIP path. The workbench validates the directory and ZIP, checks CRC and compares member hashes, then publishes a new file on success. If the original ZIP is available, the report also lists changed, added, and removed members. Approved exceptions tied to another ZIP digest require fresh approval.

---

## 简体中文

### 项目介绍

ComicFlow Validator 是一款面向 AI 漫剧创作者的开源桌面工具。

项目旨在减少素材交付过程中重复的人工检查工作，提高漫剧制作流程的可靠性。

### 当前可用检查

- 图片完整性和尺寸检查
- 图片宽高比例检查
- ZIP 成员及 CRC 检查，基础压缩包模块可计算 SHA-256 指纹
- 文件夹及 ZIP 交付报告，可用 JSON 配置必需文件、目录和允许的扩展名
- 通过已安装故事板工作流的校验脚本检查完整交付包

### 设计原则

- 本地优先：用户素材保留在本地电脑。
- 只读检查：不修改原始制作素材。
- 结果透明：每个检查结果都有明确依据。
- 易于使用：面向独立创作者和小型制作团队。

### 当前开发状态

版本：0.1.0

**项目处于早期开发阶段。**

故事板验收支持命令行和 Windows 启动器。

### 本地运行

需要 Python 3.13。

```bash
python -m pip install -r requirements.txt
python -m src.image_checker "图片目录" --ratio 16:9
python -m src.delivery_checker "交付包.zip"
python -m pytest -q
```

验收完整故事板组时，可直接指定最终 ZIP，以及当前已安装工作流中可信的 `scripts/validate_storyboard_package.py`。ComicFlow 会先检查 ZIP，再临时解包执行故事板验收。

```bash
python -m src.delivery_checker "交付包.zip" --storyboard-validator "工作流路径/scripts/validate_storyboard_package.py"
```

若手上另有独立验收过的交付目录，可以同时提供该目录和最终 ZIP，逐文件比对 SHA-256。

```bash
python -m src.delivery_checker "交付目录" --storyboard-validator "工作流路径/scripts/validate_storyboard_package.py" --zip "交付包.zip"
```

默认严格验收。历史包复核可显式添加 `--allow-legacy`。`--rules` 可为交付目录追加项目专用的文件规则。人物身份、真实机位、画面可读性、动作连续性及成片仍需人工复核。

跨工作区复验时，可加 `--review-missing-sources`，把本地路径失效的复用原图报告为「未验证」。只有原图不可访问时退出码为 `3`，缺件、文件字节不符或格数不符等错误仍退出 `1`。退出码 `0` 表示自动校验无错误。

### Windows 双击或拖拽验收

1. 安装含 Tcl/Tk 的 Python 3，再运行 `python -m pip install -r requirements.txt`。如果电脑只提供 `py`，可用 `py -3 -m pip install -r requirements.txt`。启动器优先找项目 `.venv`，然后尝试 `python` 和 `py -3`，并检查依赖。
2. 双击 `ComicFlow-Windows.bat` 选择 ZIP，或在资源管理器把 ZIP 拖到该文件上。
3. 选择可信的故事板校验脚本，点击「开始验收」。可通过环境变量 `COMICFLOW_STORYBOARD_VALIDATOR` 预填脚本路径。
4. 在「验收结果」点选一条记录，查看可定位的组、镜号和对应文件。可在下方切换组内文件，也可打开「完整报告」看原始输出。预览与验收使用同一份临时 ZIP 副本，关闭窗口即清理，全程在本机工作。
5. 点「逐格复核」，按镜号查看故事板整图、对应的彩色净板和局部号，以及同镜的生产记录与 SD2 提示词。下方显示前后镜的缩略图和动作摘要，可点「上一镜／下一镜」跨组切换。拖动框选图片中的格子可放大对照。前后镜有框选时显示所选格，否则标为整板。框选范围按镜号保留到本次复核窗口关闭。复核不会改写交付包。

开发验收可在 Windows 安装依赖后运行 `python tests/windows_smoke.py`。它以合成交付包检查启动器的无参数和带 ZIP 参数两种入口，并实际操作 Tk 窗口。验证资源管理器的鼠标拖放时，可将一个 ZIP 拖到 `ComicFlow-Windows.bat` 上并检查窗口里的路径。

### SD2 单组制片

在主窗口选择当前工作流的校验脚本，再进入「单组制片」。新建项目后，导入带版本的批准剧本、该组对白和 PNG。按镜头绑定剧本源段、净板文件和对白 ID，填写制片记录与成片要求。镜头移动时，来源 ID 保持稳定，播放镜号与净板局部号按新顺序生成。

保存项目时保留同名的 `.assets` 素材目录与 `.assets.sqlite3` 登记文件，方便后续恢复和复验。调整顺序后先按新格号检查实际图片，再打开「生成逐格复核预览」。确认画面后运行「验收并导出 ZIP」，两份 TXT 和 README 由同一份镜头清单生成。选择原包可比对成员变化。制片、复核和打包在本地运行。

#### 文本制片

在单组制片点「文本制片」。本地可以预排批准整句和九图预算。对白 JSON 每条保留 `id`、`speaker` 和完整原文 `text`。同一 ID 有多句时，可填 `sentence_ends`，例如对白 `Hold here. Stay clear.` 用 `[11, 22]` 划分两句。终点为零起点、不包含终点的字符位置，空格可放在相邻两段任一侧。选择本组使用的候选，再在镜头中分配实际发声区间。跨组续说可载入上一组项目核对退出状态。首组仍有同一 ID 的余文时，预览和 ZIP 中也会生成 `待制作分镜.txt`。

「文本模型与历史」可选择已有服务预设或自定义 OpenAI 兼容接口。填写支持文本输出的模型 ID 和 API Key，选择批准剧本行段后查看即将发送的内容。确认后调用该服务。三种任务提供分镜、状态交接和 SD2 动作与声音建议。分镜建议采纳后先核对对白、人数、设备状态与净板。SD2 建议只写入镜头的成片动作和声音栏。交接建议由用户确认并录入。候选及编辑版本保存在本地项目，API Key 只在本次软件运行期间使用。

#### 图像制片

「图像制片」提供文生图、参考图生图和局部编辑。按服务商和当前预设选择可用模式。用途包括角色、道具 / HUD、场景、故事板和净板。生成净板时，选择已有批准故事板和目标镜头，软件将该镜的机位信息和组内局部号加入提示。可在提交前查看实际用途、提示词、接收地址和每张参考图的批准版本。

| 预设 | 接口 |
| --- | --- |
| 火山方舟 Seedream、OpenAI GPT Image、Google Gemini、阿里云百炼千问和万相、xAI Grok Imagine、OpenRouter | 文生图、批准参考图生图、局部编辑。允许的参考图张数按当前预设显示。填写其他模型 ID 前核对其实际能力。 |
| 智谱 CogView、百度千帆、硅基流动 | 当前预设提供文生图。 |
| 腾讯云混元 | 文生图和单参考图异步任务。输入 SecretId 和 SecretKey，重开项目后可用保存的任务编号查询。 |
| 自定义 OpenAI Images 兼容 | 适用于支持相应 Images 协议的地址。 |

百炼填区域工作空间的 API 基础地址，末尾到 `/api/v1`。火山方舟可填写图像模型 ID 或开通的推理接入点。预设已做模拟协议测试，真实账号、模型权限、地区和实际画质需用各自的 Key 实测。密钥只在本次运行期间使用。

异步提交、结果和参考图的 SHA-256 存在项目内。返回结果放在同名的 `.candidates` 目录，确认画面、版本与实际核图记录后才加入批准图像。局部编辑先在批准原图和候选图上各框选对应区域，再用批准原图作底合成。软件重新解码合成图并核对选区外像素。若局部需要按尺寸对齐，界面会提示。批准同名修订时保留原图和既有来源，将正式净板绑定指向新版本。出包时只包含批准图和正式制片记录。新任务超时后可按任务编号查询，或先到服务商后台核对受理状态。

### 资产登记和返修打包

- 打开「资产与返修」，建一个本地 `.sqlite3` 资产登记库，填写批准原图、资产 ID 和版本。对旧包可在「原引用」填写生产记录里的旧路径。新版生产记录可使用 `asset:资产ID@版本`。换电脑时保留登记库，在新素材目录按 SHA-256 找回；同名异图或重新编码的图不会通过直接复用校验。选择过的登记库会供本次运行的验收使用，命令行也可传 `--asset-registry`。
- 返修打包前，可先验收原 ZIP，再输入完整镜号查看故事板、所指向的净板、两份 TXT 和已有 README。修复实际文件后，选择返修目录和一个新的 ZIP 文件名。工具复验目录、ZIP CRC 和逐文件 SHA-256，验证通过后才发布，并列出相对原包修改、新增和删除的文件。界面可保存一份「问题—位置—修复—复验」报告。绑定旧包 SHA-256 的例外需要针对新包重新批准。

常规长对白组确有获批的超六格例外时，直验 ZIP 可加 `--panel-exception 文件.json`，也可在启动器选择该 JSON。填写 `zip_sha256`（最终 ZIP 的小写 SHA-256）、`group`（如 `SB05`）、`panels`（批准的格数，7–12）和 `reason`（单行批准理由）。例外只适用于该 ZIP，该组及该条六格规则。

### 生图前预检

点「生图前预检」，按单组填写主角、配角、道具/HUD、场景的计划图片张数。故事板固定计 1 张，窗口显示九图预算的剩余量或超量。

英文对白可导入 JSON 或直接粘贴。选好工作流的校验脚本后，点「预排完整句」，程序调用同目录的 `plan_english_dialogue.py`，显示候选组词数、说话人、源对白 ID 和原文区间。每条是一个批准的完整发声句，格式如 `[{"id":"D001","speaker":"角色甲","text":"Hold the door."}]`。跨镜或跨组续说时可使用原有 `start` 和 `end` 字段。候选分组需结合动作承接和镜头内容确认。两项预检均在本机完成。

### 可选 AI 辅助看图

在窗口选择并预览一张 PNG、JPEG 或 WebP，点击「AI 辅助看图」。可选豆包（火山方舟）、千问（阿里云百炼）、Claude、OpenAI、Gemini、Kimi、GLM（智谱）、混元（腾讯云 TokenHub）、千帆（百度智能云）、硅基流动、OpenRouter、Grok 和自定义 OpenAI 兼容接口。

填写支持图片输入的模型 ID 和该服务的 API Key，可按账号地域更换 HTTPS 基础地址。确认后仅发送选中图片和看图提示。超过 6 MiB 的预览图片会先在本机生成压缩副本，发送窗口会标明。Key 只保留在当前运行内存中，模型建议单独展示供人工复核，本地验收结论照常保留。

---

**Project:** ComicFlow Validator  
**Development:** Open Source  
**Platform:** Windows (initial target)
