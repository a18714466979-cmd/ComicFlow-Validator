# 更新日志 / Changelog

漫剧镜序制片台 · Comic Sequence Studio

## 2.0.0 · 2026-11-28

### 简体中文

- 软件定名为「漫剧镜序制片台」（Comic Sequence Studio），体现从分镜、资产到整集制作和交付的工作范围。增加版本历史，方便定位每批改动和验收记录。
- 新名称在首页、窗口和安装说明统一展示。点击首页版本号，或打开「帮助 → 更新日志」，可在软件里离线查看这份记录。
- 调整批量制作中心的验收交付按钮布局，让窄窗口里仍可查看覆盖情况和导出选项。
- 解压 Windows 包后，先运行 `Comic-Sequence-Studio-Setup.bat` 安装依赖，再运行 `Comic-Sequence-Studio.bat` 启动。项目仍使用 `.cfproject`、`.cfbatch` 和 `.cfecom`。
- 已报告的 3D 导演台部分姿势的人偶接合问题仍待复现定位。当前版本使用既有素材预览和动作卡。
- 验证本版时，可按安装包里的 `REVISION.txt` 核对提交号，再查看对应运行的 Windows 安装与桌面验证结果。[Windows 验证记录](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

### English

- The name Comic Sequence Studio reflects the range of the application, from shots and assets to episode production and delivery. A release history documents each batch of changes and its verification.
- The new name appears on the home page, in windows, and in the installation guide. Click the version on the home page or open **Help → Changelog** to read this history offline.
- The batch review footer keeps coverage and export controls in view at narrow window widths.
- Extract the Windows package, run `Comic-Sequence-Studio-Setup.bat` to install dependencies, and run `Comic-Sequence-Studio.bat` to launch. Projects use `.cfproject`, `.cfbatch`, and `.cfecom`.
- A reported issue with visible gaps at the mannequin's joints in the 3D Director Desk is awaiting reproduction and diagnosis. This release uses the existing media preview and action cards.
- To check this release's validation, match the commit in the package's `REVISION.txt` to the corresponding Windows installation and desktop validation run. [Windows validation runs](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

## A 版基线 / A layout baseline · 2026-11-28

### 简体中文

- 故事板制作首页按整集制作顺序给出五个入口，以便直接找到当前工序。批量制作中心显示当前选中的故事板组、逐格复核和跨组交接状态，为导出前的检查提供入口。
- 提交 `bf2fde3` 的 Windows 安装和桌面验证通过。用中英文在 125% 和 150% 显示比例下操作了首页与批量流程。本次自动测试 299 项通过，3 项可选外部验证跳过。[A 版 Windows 验证](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46105244726)

### English

- The storyboard home page arranged episode production in five steps so creators could find the current stage. The batch center showed the selected group, panel review status, and handoff status before export.
- Commit `bf2fde3` passed Windows installation and desktop validation. The home page and batch workflow were exercised in both languages at 125% and 150% display scaling. The automated run passed 299 tests and skipped three optional external-validator checks. [A layout Windows validation](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46105244726)

## 记录约定 / Recording releases

每版记录日期、版本、改动原因、受影响的入口、兼容性、已知问题、验证范围和对应提交或测试链接。计划中的工作在交付后写入版本条目。

For each release, record its date and version, what changed and why, affected entry points, compatibility, known issues, and verification scope with the relevant commit or test link. Add planned work to a release entry after delivery.
