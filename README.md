# ComicFlow Validator

**面向 Seedance 2.0 的 Windows 漫剧制片工作台**

把剧本、分镜、资产、故事板、提示词和 ZIP 交付串成一条流程。重点是把容易引起返工的问题尽量拦在生成前，减少所需的 Seedance 2.0 试生成。

[下载当前 Windows 试用 ZIP](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46084287357/artifacts/15238043205) · [历次 Windows 构建](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production) · [试用指南](https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/WINDOWS-TRYOUT.md) · [English](#english)

## 工作台有什么

| 页面 | 功能 |
| --- | --- |
| **故事板制作** | 剧本创作 → 分镜拆分 → 资产分析，可带着同一原稿和镜头接续。支持资产图、黑白故事板和彩色净板、角色服装与动作参考、Seedance 2.0 提示词、排版、相邻组交接和 ZIP 交付。已有稿件或素材可从对应工序直接导入。 |
| **检查验收** | 检查图片尺寸、比例和文件大小，复核 ZIP 成员、CRC 和文件指纹，逐格对照故事板、净板、制作记录和提示词，查看同组、跨页与跨组的镜头衔接。 |
| **API 接入** | 为文本创作、AI 审图和图像生成分别配置模型。预览并确认发送后调用所选服务。预检、排版、人工核图和打包可在本机进行。 |

## 怎么减少 SD2 抽卡

- **先锁镜头再生图。** 固定原稿版本、实际发声对白、镜头顺序和入画人数。清楚指明角色参考、取景范围、动作起止和须延续的手、道具、设备状态。
- **把参考材料核在提交前。** 预检单组九图预算。并排检查故事板、彩色净板和文字，提前发现重复景别、跨镜跳变、漏件或机位对应错误。
- **有问题修到具体位置。** 记录批准原图和版本，定位受影响的镜头、字段和像素窗口，支持以原图为底进行局部返修。打包后重新打开最终 ZIP 核对。

这些步骤减少的是输入错误、素材漂移和整组返工带来的可预防试错。模型仍有随机性，实际减少多少取决于项目和输入质量。ComicFlow 输出供 Seedance 2.0 使用的素材和提示词，成片生成在 Seedance 2.0 服务中进行。换用其他视频模型时，需要按模型调整参考图和提示词。

## 制作规则与检查边界

| 规则 | 当前执行方式 |
| --- | --- |
| **英文影片制作 v14.10.3** | 按批准的完整发声句预排，每组最多 60 个实际发声英文词。分镜中不得连续用同一中景或大全景表达同一目的。打斗禁止连续三镜既同景别又同角度。确有动作匹配的相邻镜头须看实图核对。 |
| **中文影片制作 v14.8.8** | 每组最多 100 个实际发声字符，超出按批准的自然停顿顺延。相邻独立镜头，包括组间边界，应拉开景别。真正的单机位连续动作按一镜处理，机位变换须保留轴线和固定背景。 |
| **生图前与交付复核** | 分镜和故事板生成提示会写入对应规则。「镜头清单 → 景别与角度预检」会按已登记字段定位重复，预警进入生图确认和画面确认。跨组可并排核对前组末镜和后组首镜。实际构图、真实机位、身份和动作承接由人看图确认。 |
| **正式验收** | 至多九张交付图，核对图件命名、比例、编号、批准对白和两份 TXT 的对应关系。完整规则检查需选对应版本的故事板校验脚本。文件检查和视觉验收分别记录。 |

## 试用

1. 下载并解压 Windows 试用 ZIP。安装带 Tcl/Tk 的 Python 3.13，再双击 `ComicFlow-Setup.bat`。
2. 双击 `ComicFlow-Windows.bat`。可以打开新项目，也可以把已有 `.cfproject` 或 ZIP 拖到启动器。
3. 用 `Examples` 里的中英文示例体验排版、逐格复核、单组和相邻组交付。

当前 Windows 工作台代码在 [开发分支](https://github.com/a18714466979-cmd/ComicFlow-Validator/tree/codex/chinese-production)。试用 ZIP 是 GitHub Actions 构建产物。当前链接到期后，可到上方构建列表打开通过的运行并下载试用包。

## English

**ComicFlow is a Windows production and review workbench for ByteDance Seedance 2.0.**

It connects script writing, shot planning, asset analysis, reference preparation, storyboard generation, SD2 prompts and validated ZIP delivery. Each stage also accepts existing local work. The review workspace compares shots across panels, pages and groups. The API workspace separates text drafting, visual inspection and image generation.

ComicFlow is designed to reduce avoidable regenerations by checking approved dialogue, shot framing and the nine-image budget before submission, and by tracing fixes to the affected images or shots. The English and Chinese workflows have separate dialogue and framing rules. Automated framing alerts use recorded shot fields. Camera geometry, composition, continuity and generated videos still need visual review.

[Windows trial](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46084287357/artifacts/15238043205) · [Setup guide](https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/WINDOWS-TRYOUT.md) · [Workbench source](https://github.com/a18714466979-cmd/ComicFlow-Validator/tree/codex/chinese-production)
