
# ComicFlow Validator

**A Local-First Desktop Tool for AI Comic Production**

一款面向 AI 漫剧创作者的本地素材验收工具。

[English](#english) | [简体中文](#简体中文)

---

## English

### Overview

ComicFlow Validator is an open-source desktop tool designed to help AI comic creators validate production assets and delivery packages.

The goal is to reduce repetitive manual checks and improve the reliability of production workflows.

### Planned Features

- Image integrity and dimension checks
- Aspect ratio validation
- File naming and sequence checks
- ZIP archive integrity and CRC validation
- Automated validation reports

### Design Principles

- Local-first: Files remain on the user's computer.
- Read-only: Original production assets are not modified.
- Transparent: Every validation result should have a clear reason.
- Accessible: Designed for independent creators and small teams.

### Current Status

Version: 0.1.0

**Early development.**

The current version is a basic application bootstrap.
Automated asset validation features have not yet been implemented.

### Run from Source

Requirements: Python 3.13 (tested).

```bash
python src/main.py
```

---

## 简体中文

### 项目介绍

ComicFlow Validator 是一款面向 AI 漫剧创作者的开源桌面工具。

项目旨在减少素材交付过程中重复的人工检查工作，提高漫剧制作流程的可靠性。

### 计划实现的功能

- 图片完整性和尺寸检查
- 图片宽高比例检查
- 文件命名及编号连续性检查
- ZIP 压缩包完整性及 CRC 检查
- 自动生成验收报告

### 设计原则

- 本地优先：用户素材保留在本地电脑。
- 只读检查：不修改原始制作素材。
- 结果透明：每个检查结果都有明确依据。
- 易于使用：面向独立创作者和小型制作团队。

### 当前开发状态

版本：0.1.0

**项目处于早期开发阶段。**

当前版本仅完成基础程序框架，自动化素材验收功能尚未实现。

### 本地运行

需要 Python 3.13。

```bash
python src/main.py
```

---

**Project:** ComicFlow Validator  
**Development:** Open Source  
**Platform:** Windows (initial target)
