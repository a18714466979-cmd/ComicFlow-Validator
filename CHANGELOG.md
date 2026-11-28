# 更新日志 / Changelog

漫剧镜序制片台 · Comic Sequence Studio

## 2.6.0 · 2026-11-28

### 简体中文

- 剧本、分镜、资产分析、资产图、故事板图、提示词和组交付可在主窗口打开任务标签。可带着项目和已选剧本走下一步，也可从本地单组项目进入中间工序。
- 资产分析清单可带入生图的补充需求。批准图像、素材选择与放大、排版和角色服装可从相关任务进入，结果保存到当前组。
- 同一组不同工序可交替保存。两处同时改动同一个字段时，软件提示冲突并保留当前草稿。

### English

- Script writing, shot planning, asset analysis, asset images, storyboard images, prompts and group delivery open as task tabs. Continue with the current group and selected script, or open an existing local project at a later stage.
- Carry asset analysis into the image brief. Open approved images, image selection, enlargement, layout and costumes from the relevant task, and save the result to the current group.
- Save independently across stages of one group. If two edits change the same field, the workbench flags the conflict and keeps the current draft available.

## 2.5.0 · 2026-11-28

### 简体中文

- 人物动作编排新增「对话与站位」。试用版提供双人平视中景同框、双人过肩正反打、三人三角站位接话。每组含一张俯视站位图与两幅 16:9 镜头图，支持离线查看和放大。
- 给 A、B、C 对应上项目角色，可将当前镜头加到动作编排草稿，或应用到本组已有分镜。应用分镜时只写入景别、机位/角度、机位空间和人物站位，保留批准对白、镜头顺序及资产。可在保存前核对写入值。

### English

- Action sequencing adds Dialogue & blocking. The preview includes three samples: an eye-level medium two-shot, an over-the-shoulder shot and reverse, and a three-person triangle with an interjection. Each contains an overhead plan and two 16:9 frames with offline enlargement.
- Map A, B and C to project characters, then add the view to the action draft or apply it to an existing shot in the group. Preview the framing, camera angle, camera position and blocking before writing those fields. Approved dialogue, shot order and assets stay as recorded.

## 2.4.0 · 2026-11-28

### 简体中文

- 五个一级入口固定在主窗口。人物动作编排在右侧打开为任务标签。同一个项目重复打开时回到原标签，窄窗口可从「已打开任务」找回其他标签。
- 动作卡图库和单帧放大预览在任务页内切换。可并排打开不同单组项目，切去检查验收再返回时保留编辑状态。未保存的任务提供继续编辑、放弃更改并关闭和保存并关闭三个选项。
- 试点覆盖故事板制作首页及单组镜头清单的人物动作编排入口。3D 导演台继续使用独立窗口。

### English

- Keep the five main workspaces in view and open action sequencing as a task tab. Opening the same project again selects its existing tab. The Open tasks menu lists tabs that do not fit.
- Browse cards and enlarge individual frames within the task. Switching workspaces preserves each project's editing state. When closing a draft, choose Keep editing, Discard and close, or Save and close.
- The pilot covers the action sequencing entry points on the production home and the single-group shot list. The 3D Director Desk opens in its own window.

## 2.3.0 · 2026-11-28

### 简体中文

- 内置 3D 导演台新增「动作片段」，可编排最长 5 秒的表演。角色分别记录位置、朝向和关节姿势，支持关键帧编辑、撤销、过渡、停顿、拖动和循环预览。
- 道具轨在指定时刻切换持有者和手，可用来预演两人递物。相机独立设置，片段随导演台工程 JSON 保存，可重新打开编辑。
- 当前批次提供本地编辑和预演。参考视频的保存与项目接入安排在下一批。[Windows 验证记录](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

### English

- The built-in 3D Director Desk adds Action clip for performances up to five seconds. Separate character tracks key position, facing and joints, with editable timing, undo, interpolation, holds, scrubbing and looping.
- Prop tracks switch the holder and hand at keyed times. Camera controls remain independent. Clips save with the editable Director Desk project JSON.
- This version provides local animation editing and preview. Reference video and project handoff are scheduled for the next phase. [Windows validation runs](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

## 2.2.0 · 2026-11-28

### 简体中文

- 人物动作编排新增「浏览动作卡」。9 类 53 张内置卡均有大封面和三帧预览，可查看起始姿势、关键变化和结束状态。中英文界面共用同一套随包图。
- 把动作卡加入项目后，预演格和相邻卡对照可显示内置示意图。已挂的项目参考图优先显示。内置图用于选卡和编排，正式交付仍使用项目已批准的图件。
- 验证记录可按安装包里的 `REVISION.txt` 查询。[Windows 验证记录](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

### English

- Action sequencing now includes a visual action card browser. All 53 built-in cards across nine categories have a cover and three frames showing the start, key change and end. The same offline artwork is available in both interface languages.
- Sequence panels and adjacent-card review show the built-in illustration after adding a preset. Project reference images take precedence. Formal deliveries use the project's approved images.
- Match the package revision in `REVISION.txt` to the installation and desktop verification run. [Windows validation runs](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production)

## 2.1.1 · 2026-11-28

### 简体中文

- 修复内置 3D 导演台程序化人偶的躯干、骨盆和四肢接合问题。摆姿势和播放动作时，关节继续跟随各自的旋转中心。
- 核对弯腰、转身、下蹲和抬臂，以及动作预览、截图与保存后打开。已保存的导演台工程继续使用原有姿势和动作数据。
- 素材库和预览关闭时，在界面线程释放预览图片与控件资源。
- Windows 已复验内置人偶的摆姿势、工程重开、播放和取图，以及素材库关闭和交付流程。[2.1.1 Windows 验证](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46111175088)

### English

- Repair the joints of the built-in procedural mannequin in the 3D Director Desk. The torso, pelvis and limbs stay connected as their joints rotate in the editor and during playback.
- Verify bending, twisting, crouching and arm raises, plus playback, capture and reopening a saved project. Existing Director Desk projects continue to use their saved pose and motion data.
- The media library and detail preview release their display resources on the UI thread when closed.
- Windows verification covered built-in mannequin posing, reopening, playback and frame capture, as well as media-library teardown and delivery workflows. [2.1.1 Windows verification](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46111175088)

## 2.1.0 · 2026-11-28

### 简体中文

- 新增图片与视频素材库。可在单组批准图像、批量公共资产、生图参考图及电商资料中按画面找素材。用可调大小的方形卡片查看完整画幅，双击看细节。
- 场景、人物、道具、待分类可筛选与批量编辑。支持横图、竖图、故事板和视频的预览。视频可查看时长、拖动进度、播放及选择封面帧。
- 分类和封面保存到各项目自己的素材索引。图片和视频保留原文件及比例。正式交付仍使用已批准和已绑定的资产。
- Windows 安装版验证通过，覆盖 101 个混合素材、双语高缩放、分类和封面保存，以及单组、生图参考、批量和电商四个入口。[2.1.0 Windows 验证](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46109376183)

### English

- Browse images and videos from approved group images, batch shared assets, image-generation references, and e-commerce source materials. Square cards preserve the full frame and can be resized. Open a card for a larger preview.
- Filter or bulk-edit scenes, characters, props, and unclassified media. Preview landscape and portrait images, storyboards, and videos. Video previews show duration and support seeking, playback and choosing a poster frame.
- Categories and poster frames are saved in each project's media index. Source files and their aspect ratios are preserved. Formal delivery still uses the approved and linked production assets.
- The 2.1.0 Windows installation passed tests for 101 mixed files, bilingual high-scaling layouts, saved categories and covers, and the group, image picker, batch and e-commerce media entry points. [2.1.0 Windows verification](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46109376183)

## 2.0.0 · 2026-11-28

### 简体中文

- 软件定名为「漫剧镜序制片台」（Comic Sequence Studio），体现从分镜、资产到整集制作和交付的工作范围。增加版本历史，方便定位每批改动和验收记录。
- 新名称在首页、窗口和安装说明统一展示。点击首页版本号，或打开「帮助 → 更新日志」，可在软件里离线查看这份记录。
- 调整批量制作中心的验收交付按钮布局，让窄窗口里仍可查看覆盖情况和导出选项。
- 解压 Windows 包后，先运行 `Comic-Sequence-Studio-Setup.bat` 安装依赖，再运行 `Comic-Sequence-Studio.bat` 启动。项目仍使用 `.cfproject`、`.cfbatch` 和 `.cfecom`。
- 已报告的 3D 导演台部分姿势的人偶接合问题仍待复现定位。当前版本使用既有素材预览和动作卡。
- 2.0.0 的 Windows 安装、两个日志入口、双语高缩放和交付样例已复验。[2.0.0 Windows 验证](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46108317565)

### English

- The name Comic Sequence Studio reflects the range of the application, from shots and assets to episode production and delivery. A release history documents each batch of changes and its verification.
- The new name appears on the home page, in windows, and in the installation guide. Click the version on the home page or open **Help → Changelog** to read this history offline.
- The batch review footer keeps coverage and export controls in view at narrow window widths.
- Extract the Windows package, run `Comic-Sequence-Studio-Setup.bat` to install dependencies, and run `Comic-Sequence-Studio.bat` to launch. Projects use `.cfproject`, `.cfbatch`, and `.cfecom`.
- A reported issue with visible gaps at the mannequin's joints in the 3D Director Desk is awaiting reproduction and diagnosis. This release uses the existing media preview and action cards.
- The 2.0.0 Windows install, both changelog entry points, bilingual high-scaling layouts and sample deliveries passed verification. [2.0.0 Windows verification](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46108317565)

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
