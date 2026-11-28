# 漫剧镜序制片台 · Comic Sequence Studio

面向字节跳动 **Seedance 2.0** 的 Windows 漫剧工作台。把一集定稿带进来，拆成分镜和故事板组，复用角色、场景和道具，最后交付每组的参考图与视频提示词。已有分镜、图片或交付 ZIP 时，可以直接从对应工序开始。

**[下载 Windows 试用包 v2.9.0][trial]** · [Windows 验证记录][run] · [安装与操作指南][guide] · [更新日志][changes] · [工作台源码][source] · [English](#english)

## 第一次打开

1. 登录 GitHub，下载并解压 `Comic-Sequence-Studio-Windows.zip`。安装 Windows 版 Python 3.13，保留 Tcl/Tk 和 pip。
2. 首次双击 **`Comic-Sequence-Studio-Setup.bat`** 安装依赖。看到 `COMIC_SEQUENCE_STUDIO_SETUP_OK` 后关闭窗口。以后双击 **`Comic-Sequence-Studio.bat`** 启动。
3. 有 TXT 或 Markdown 剧本，点「新建项目」并导入原稿。有保存过的 `.cfproject`，点「继续已有项目」。手头是交付压缩包，点「验收已有 ZIP」。想先体验，打开「使用教程 → 从已有分镜练习」。

本页所在的 `main` 分支保留了早期校验器源码。完整桌面工作台在 [codex/chinese-production][source]。试用包由 GitHub Actions 保存 30 天。下载链接到期后，可在[制作分支的 Windows 构建列表][builds]选择近期成功的运行，从 **Artifacts** 下载同名 ZIP。

## 五个工作区

| 入口 | 可以完成什么 |
| --- | --- |
| **故事板制作** | 写剧本、拆分镜、分析资产，将已选稿件和镜头直接交给下一步。按场景、人物和道具查看大图，制作资产图、故事板和净板，编写 SD2 提示词，导出单组 ZIP。「批量制作中心」按集导入定稿、追踪原文到镜头、复用批准资产、处理候选、核对跨组交接，最后导出整集或多集。 |
| **电商信息流视频复刻** | 导入本地参考视频，检查候选切点和分镜，登记自己的产品名称及图片，重建所需资产，输出竖屏 9:16 故事板、分镜说明、SD2 提示词和交付 ZIP。 |
| **检查验收** | 查看实际图像、像素尺寸、比例和文件大小，检查 ZIP 成员、CRC 和 SHA-256。并排检查故事板、净板、对白及相邻组的首尾镜，回到原项目返修。 |
| **API 接入** | 文本创作、图片审核、图片生成分别选择服务和模型。同一服务可以承担多种任务，所选模型须支持对应输入和输出。预览材料并确认发送后，才会调用所配置的服务。 |
| **使用教程** | 中英文共用 38 个详细主题，各有一套可放大的界面截图。可从剧本、已有分镜、电商视频、多集项目或交付返修五种离线练习开始，在工具里点「本页帮助」后可返回原任务。 |

要设计多人表演，可从「故事板制作 → 人物动作编排 → 对话与站位」查看双人中景、过肩正反打和三人站位的俯视图与镜头图。另有 53 张动作卡、23 套服装参考，以及带独立人物关键帧、定时道具交接和最长 5 秒预演的内置 3D 导演台。Windows 使用导演台需要 Edge WebView2 Runtime。

## 制作规则怎样减少返工

- **按项目选择英文或中文影片制作。** 界面语言可以独立切换。英文规则 v14.10.4 和中文规则 v14.8.8 分别处理对白、分组和机位。英文导出的逐镜提示词绑定到具体 PNG 和板格，保留批准英文对白。中文按每组最多 100 个实际发声字符规划。
- **生图前检查可判断的错误。** 英文预检可拦截有记录的相邻中景或大全景重复同一叙事目的，以及标记为打斗的组三镜同景别同角度。九图预算、对白与两份 TXT、素材版本及格号可提前核对。英文流程内置离线严格校验器，中文正式交付需要另选可信的中文规则校验脚本。
- **逐格核对画面后再打包。** 景别警告依据已填镜头字段。实际机位、人物身份、动作接续和画面质量需要看图确认。这个流程针对可预防的返工，尚无实测的试生成降幅。素材和提示词最终提交到 Seedance 2.0 服务生成成片。其他视频模型的输入限制和提示词格式可能不同。

## 这个试用包验证了什么

v2.9.0 的 Windows 构建通过了自动化测试、生成 ZIP、解压安装、桌面操作与样例交付检查。样例覆盖中英文单组、相邻两组、局部返修及重新打包。上述检查不含真实付费模型调用或最终视频的动态、口型与音频质量验收。[查看该版本的 GitHub Actions 步骤][run]

## English

**Comic Sequence Studio** is a Windows workbench for preparing and reviewing storyboard deliveries for ByteDance Seedance 2.0. Start with an approved script, carry shots and references into the next stage, or open existing local work. The output is a group, episode or series ZIP for production.

**[Download the Windows v2.9.0 trial][trial]** · [Verified Windows build][run] · [Setup and walkthrough][guide] · [Changelog][changes] · [Workbench source][source]

1. Sign in to GitHub, download and extract `Comic-Sequence-Studio-Windows.zip`, then install Python 3.13 with Tcl/Tk and pip. Run `Comic-Sequence-Studio-Setup.bat` once and `Comic-Sequence-Studio.bat` to launch.
2. Choose **New project** for a text or Markdown script, **Resume saved project** for a `.cfproject`, or **Validate an existing ZIP** for a delivery. **Tutorial** includes five offline exercises and 38 illustrated topics in each interface language.
3. **Storyboard production** connects script, shots, assets, wardrobe, action blocking, boards, clean plates, SD2 prompts and delivery. Its batch center tracks script coverage and handoffs across groups and episodes. **E-commerce video recreation** starts with a local video and your product photos and produces vertical storyboard groups. **Inspection and validation** checks images and archives and supports side-by-side visual review. **API connections** configures text, vision and image-generation models separately.

English and Chinese film workflows use separate dialogue, framing and delivery rules. English strict validation is bundled. Formal Chinese delivery requires a trusted Chinese validator script. Preflight uses recorded fields to flag avoidable input errors. Composition, identity and continuity require review of the actual frames. Submit the exported material to Seedance 2.0 for final rendering.

The linked Windows job tests installation, desktop interactions and sample delivery archives. Live paid API calls and final video or audio quality are outside that test. The desktop source is on [codex/chinese-production][source]. The default branch contains the original validator. Trial downloads expire after 30 days. If a link has expired, open a recent successful [Windows build][builds] and download the ZIP under **Artifacts**.

[trial]: https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46133461516/artifacts/15259185095
[run]: https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/runs/46133461516
[builds]: https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production
[guide]: https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/WINDOWS-TRYOUT.md
[changes]: https://github.com/a18714466979-cmd/ComicFlow-Validator/blob/codex/chinese-production/CHANGELOG.md
[source]: https://github.com/a18714466979-cmd/ComicFlow-Validator/tree/codex/chinese-production
