
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

On Windows, install the requirements with the Python 3 interpreter used by the launcher. Double-click `ComicFlow-Windows.bat` and pick a ZIP, or drop a ZIP on the `.bat` file in Explorer. Select the trusted workflow validator, then start the check. Set `COMICFLOW_STORYBOARD_VALIDATOR` to prefill its path. The result stays in the console until you press a key.

For an approved extra-panel exception to the six-panel dialogue rule, pass `--panel-exception file.json` when validating a ZIP directly, or select the JSON in the launcher. The entry is tied to one ZIP SHA-256, one group such as `SB05`, its approved `panels` count (7–12), and a one-line `reason`. Only the matching six-panel-rule diagnostic is treated as an approved exception.

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

1. 用启动器所用的 Python 3 安装依赖，有 `py` 时运行 `py -3 -m pip install -r requirements.txt`，否则使用 `python -m pip install -r requirements.txt`。
2. 双击 `ComicFlow-Windows.bat` 选择 ZIP，或在资源管理器把 ZIP 拖到该文件上。
3. 选择可信的故事板校验脚本，点击「开始验收」。结果显示在命令窗口。可通过环境变量 `COMICFLOW_STORYBOARD_VALIDATOR` 预填脚本路径。

常规长对白组确有获批的超六格例外时，直验 ZIP 可加 `--panel-exception 文件.json`，也可在启动器选择该 JSON。填写 `zip_sha256`（最终 ZIP 的小写 SHA-256）、`group`（如 `SB05`）、`panels`（批准的格数，7–12）和 `reason`（单行批准理由）。例外只适用于该 ZIP，该组及该条六格规则。

---

**Project:** ComicFlow Validator  
**Development:** Open Source  
**Platform:** Windows (initial target)
