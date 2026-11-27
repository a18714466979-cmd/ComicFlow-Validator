
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

The desktop entry point is a bootstrap. Validation is available from the command line.

### Run from Source

Requirements: Python 3.13 (tested).

```bash
python -m pip install -r requirements.txt
python -m src.image_checker "path/to/images" --ratio 16:9
python -m src.delivery_checker "path/to/delivery.zip"
python -m pytest -q
```

For a complete storyboard package, provide the final ZIP and the trusted `scripts/validate_storyboard_package.py` from your installed storyboard workflow. Install NumPy in the same Python environment if needed. ComicFlow checks the ZIP and unpacks it temporarily for storyboard validation.

```bash
python -m src.delivery_checker "path/to/delivery.zip" --storyboard-validator "path/to/workflow/scripts/validate_storyboard_package.py"
```

When you also have an independently validated delivery folder, provide both paths to compare its files with the final ZIP by SHA-256.

```bash
python -m src.delivery_checker "path/to/delivery" --storyboard-validator "path/to/workflow/scripts/validate_storyboard_package.py" --zip "path/to/delivery.zip"
```

Strict mode is the default. Use `--allow-legacy` for historical packages. `--rules` can add project-specific preflight rules to the delivery directory. Visual identity, actual camera geometry, readability, action continuity, and video still require review.

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

桌面入口目前为启动框架。验收功能可通过命令行使用。

### 本地运行

需要 Python 3.13。

```bash
python -m pip install -r requirements.txt
python -m src.image_checker "图片目录" --ratio 16:9
python -m src.delivery_checker "交付包.zip"
python -m pytest -q
```

验收完整故事板组时，可直接指定最终 ZIP，以及当前已安装工作流中可信的 `scripts/validate_storyboard_package.py`。如当前 Python 环境缺少 NumPy，请先安装。ComicFlow 会先检查 ZIP，再临时解包执行故事板验收。

```bash
python -m src.delivery_checker "交付包.zip" --storyboard-validator "工作流路径/scripts/validate_storyboard_package.py"
```

若手上另有独立验收过的交付目录，可以同时提供该目录和最终 ZIP，逐文件比对 SHA-256。

```bash
python -m src.delivery_checker "交付目录" --storyboard-validator "工作流路径/scripts/validate_storyboard_package.py" --zip "交付包.zip"
```

默认严格验收。历史包复核可显式添加 `--allow-legacy`。`--rules` 可为交付目录追加项目专用的文件规则。人物身份、真实机位、画面可读性、动作连续性及成片仍需人工复核。

---

**Project:** ComicFlow Validator  
**Development:** Open Source  
**Platform:** Windows (initial target)
