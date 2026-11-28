# ComicFlow Validator

**面向 Seedance 2.0 的 Windows 漫剧制片工作台**

把剧本、分镜、资产、故事板、提示词和 ZIP 交付串成一条流程。重点是把容易引起返工的问题尽量拦在生成前，减少所需的 Seedance 2.0 试生成。

[下载当前 Windows 试用 ZIP](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46097994728/artifacts/15244301002) · [历次 Windows 构建](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production) · [试用指南](https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/WINDOWS-TRYOUT.md) · [English](#english)

## 工作台有什么

| 页面 | 功能 |
| --- | --- |
| **故事板制作** | 剧本创作 → 分镜拆分 → 资产分析，可带着同一原稿和镜头接续。支持资产图、黑白故事板和彩色净板、23 套内置服装参考、人物动作编排、Seedance 2.0 提示词、排版、相邻组交接和 ZIP 交付。已有稿件或素材可从对应工序直接导入。 |
| **电商信息流视频复刻** | 导入参考视频和自有产品图，检测候选切点、核对分镜、制作资产及 9:16 故事板，预览 SD2 提示词并打包。 |
| **检查验收** | 检查图片尺寸、比例和文件大小，复核 ZIP 成员、CRC 和文件指纹，逐格对照故事板、净板、制作记录和提示词，查看同组、跨页与跨组的镜头衔接。 |
| **API 接入** | 为文本创作、AI 审图和图像生成分别配置模型。按任务锁定 API 指令，区分规则和用户资料，确认后才调用所选服务。生图接口只有一个提示词字段时，软件固定将规则放在补充需求之前。预检、排版、人工核图和打包可在本机进行。 |
| **使用教程** | 中英文实机截图和简短步骤，覆盖快速开始、剧本到交付、ZIP 验收和 API 设置。可以直接打开内置示例或对应入口。 |

「人物动作编排」内置 53 张中英双语卡片。可从表演、走位、救援或刀、长枪、剑、戟等影视道具卡起步，添加姿势参考图，在 12 格或 15 格预演中对照前后动作、持物手与道具，再选择要带入正式分镜的卡片。支持读取 [3D 导演台](https://github.com/xiaozangao/3d-director-desk) 工程中的人物和道具轨迹。

在「动作参考库」选择官方片段示例，或粘贴 YouTube、优酷、腾讯视频的播放页。记下起止时间和自己的镜头笔记，可直接用笔记新建动作卡，也可追加到选中的卡。视频在浏览器播放，参考条目随单组项目保存。

第二个一级标签「电商信息流视频复刻」从本地参考视频开始。先确认自有产品名称和所需照片，再拆镜并核对原声、表演与场景。完成角色、场景、道具、产品总图与竖屏彩色故事板后，导出每组独立可用的中文分镜 TXT、Seedance 2.0 提示词和验收 ZIP。

## 怎么减少 SD2 抽卡

- **先锁镜头再生图。** 固定原稿版本、实际发声对白、镜头顺序和入画人数。清楚指明角色参考、取景范围、动作起止和须延续的手、道具、设备状态。
- **把参考材料核在提交前。** 预检单组九图预算。并排检查故事板、彩色净板和文字，提前发现重复景别、跨镜跳变、漏件或机位对应错误。
- **有问题修到具体位置。** 记录批准原图和版本，定位受影响的镜头、字段和像素窗口，支持以原图为底进行局部返修。打包后重新打开最终 ZIP 核对。

这些步骤减少的是输入错误、素材漂移和整组返工带来的可预防试错。模型仍有随机性，实际减少多少取决于项目和输入质量。ComicFlow 输出供 Seedance 2.0 使用的素材和提示词，成片生成在 Seedance 2.0 服务中进行。换用其他视频模型时，需要按模型调整参考图和提示词。

## 制作规则与检查边界

| 规则 | 当前执行方式 |
| --- | --- |
| **英文影片制作 v14.10.4** | 旧英文项目打开后直接应用新版。内置离线严格校验与整句对白预排。生成正式故事板前检查分组格数、关键分镜字段、批准对白和九图预算。已登记的相邻中景或大全景重复同一叙事目的，以及打斗组三镜同景别同角度，会被拦截。 |
| **中文影片制作 v14.8.8** | 每组最多 100 个实际发声字符，超出按批准的自然停顿顺延。相邻独立镜头，包括组间边界，应拉开景别。真正的单机位连续动作按一镜处理，机位变换须保留轴线和固定背景。 |
| **生图前与交付复核** | 分镜和故事板生成提示会写入对应规则。「镜头清单 → 景别与角度预检」会按已登记字段定位重复，预警进入生图确认和画面确认。跨组可并排核对前组末镜和后组首镜。实际构图、真实机位、身份和动作承接由人看图确认。 |
| **英文 SD2 提示词** | 自动按组号、故事板硬切指令、实际 PNG 的 `@图` 上传清单、组级约束和固定逐镜字段导出。逐镜绑定到具体的净板文件与局部号，保留批准的英文对白。默认无配乐、无字幕。 |
| **正式验收** | 至多九张交付图，核对图件命名、比例、编号、批准对白和两份 TXT 的对应关系。英文可用内置严格校验，中文使用对应脚本。实际构图、身份和动作承接仍须逐格复核。 |

## 第一次打开选哪个入口

| 手里有什么 | 从哪里开始 |
| --- | --- |
| 从零开始，或有 TXT / Markdown 剧本 | 点「新建项目」并选保存位置，软件会创建 `.cfproject`。已有原稿可在项目中点「导入批准剧本」。 |
| 有保存过的 `.cfproject` | 点「继续已有项目」。想先练习，可以打开试用包里的 `Examples/SB01.cfproject`。 |
| 有已做好的故事板交付包 | 点「验收已有 ZIP」，选原始压缩包，再点「开始验收」。 |

## 试用

1. 下载并解压 Windows 试用 ZIP。安装带 Tcl/Tk 的 Python 3.13，再双击 `ComicFlow-Setup.bat`。
2. 双击 `ComicFlow-Windows.bat`。可以打开新项目，也可以把已有 `.cfproject` 或 ZIP 拖到启动器。
3. 用 `Examples` 里的中英文示例体验排版、逐格复核、单组和相邻组交付。进入「资产图生成」选已有项目时会显示加载状态，打开项目本身不改写项目文件。

当前 Windows 工作台代码在 [开发分支](https://github.com/a18714466979-cmd/ComicFlow-Validator/tree/codex/chinese-production)。试用 ZIP 是 GitHub Actions 构建产物。当前链接到期后，可到上方构建列表打开通过的运行并下载试用包。

## English

**ComicFlow is a Windows production and review workbench for ByteDance Seedance 2.0.**

It connects script writing, shot planning, asset analysis, reference preparation, storyboard generation, SD2 prompts and validated ZIP delivery. Each stage also accepts existing local work. Action sequencing includes 53 bilingual cards, 12- and 15-panel previews, local pose image references, and 3D Director Desk route import. Selected story actions can be sent to existing or source-bound new shots. The Action reference library saves YouTube, Youku and Tencent Video playback links, time ranges and your own shot notes with each project. Open a clip in your browser, then create an action card from your notes or append them to a selected card. The ecommerce workspace imports a local reference video and approved product photography, proposes cuts, and prepares independently usable vertical storyboard groups and delivery ZIPs. The review workspace compares shots across panels, pages and groups. The API workspace separates text drafting, visual inspection and image generation. The illustrated Tutorial tab guides first-time users through these tools and opens the bundled offline example. Each request uses fixed workflow instructions before the user’s material, with a separate system message for text and visual review.

ComicFlow is designed to reduce avoidable regenerations by checking approved dialogue, shot framing and the nine-image budget before submission, and by tracing fixes to the affected images or shots. The English and Chinese workflows have separate dialogue and framing rules. Automated framing alerts use recorded shot fields. Camera geometry, composition, continuity and generated videos still need visual review.

To start, choose **New project**, **Resume saved project** (try `Examples/SB01.cfproject`), or **Validate an existing ZIP**. A `.cfproject` is the editable project that ComicFlow creates when you choose **New project**.

[Windows trial](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46097994728/artifacts/15244301002) · [Setup guide](https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/WINDOWS-TRYOUT.md) · [Workbench source](https://github.com/a18714466979-cmd/ComicFlow-Validator/tree/codex/chinese-production)
