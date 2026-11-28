
# ComicFlow Validator

**A production and review workbench for AI comics using Seedance 2.0**

面向字节跳动 Seedance 2.0 的漫剧制片工作台，贯通剧本、分镜、资产、故事板、提示词和 ZIP 交付。

[Windows 试用版构建](https://github.com/a18714466979-cmd/ComicFlow-Validator/actions/workflows/windows-smoke.yml?branch=codex%2Fchinese-production) · [安装和试用说明](WINDOWS-TRYOUT.md)

[English](#english) | [简体中文](#简体中文)

---

## English

### Overview

ComicFlow helps AI comic creators prepare and review a complete delivery for ByteDance Seedance 2.0. Its three workspaces cover storyboard production, inspection and validation, and API connections. Work through script, shots and assets in one project, or start a stage with a local file.

Approved sources, dialogue spans, shot order, camera references and the nine-image budget can be checked before submission. Reviewing adjacent panels and repairing the affected region helps avoid repeated generations and full-group rework caused by preventable input problems.

English Film Production and Chinese Film Production are designed for delivery to ByteDance Seedance 2.0. Both prepare PNG references, an SD2 prompt and a validated delivery ZIP. Other video models may be a weaker fit and can require changes to reference limits, prompt structure and shot continuity. The workbench prepares the package for submission through a separate Seedance 2.0 service. [Seedance 2.0 overview](https://seed.bytedance.com/en/seedance2_0) · [Video generation API](https://docs.volcengine.com/docs/ark/create-video-generation-task-api?lang=zh)

### Current Checks

- Image integrity and dimension checks
- Aspect ratio validation
- ZIP entry and CRC checks, with a SHA-256 digest from the archive checker
- Directory and ZIP delivery reports with optional JSON rules for required files, directories, and extensions
- Complete storyboard package validation through the installed workflow's validator

### Workflow and visual review

- Use English Film Production v14.10.3 or Chinese Film Production v14.8.8. Both keep project assets and validation local. Optional model calls send the selected material to the configured provider after confirmation.
- Shot drafting and board image prompts include the camera guidance for the active workflow. A local preflight flags repeated recorded framing, with additional guidance for three same-size, same-angle shots in a group marked as a fight.
- For camera geometry, composition, identity and action continuity, compare the actual panels and clean plates. The text checks flag review points. Final Seedance 2.0 output needs a separate viewing pass.

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

On Windows, install the requirements for Python 3 with Tcl/Tk. The launcher prefers the project's `.venv`, then tries `python` and `py -3` for an interpreter with its desktop dependencies. Double-click `ComicFlow-Windows.bat`. Choose **New project** to create a `.cfproject`, **Resume saved project** to open one (try `Examples/SB01.cfproject`), or **Validate an existing ZIP** to check a delivery archive. You can also drop a ZIP on the `.bat` file in Explorer. Select the trusted workflow validator, then start the check. Set `COMICFLOW_STORYBOARD_VALIDATOR` to prefill its path. The result table shows groups, shot IDs and filenames when the validator identifies them. Select a row to preview its text or image in the window, or switch to the full report tab.

For an approved extra-panel exception to the six-panel dialogue rule, pass `--panel-exception file.json` when validating a ZIP directly, or select the JSON in the launcher. The entry is tied to one ZIP SHA-256, one group such as `SB05`, its approved `panels` count (7–12), and a one-line `reason`. Only the matching six-panel-rule diagnostic is treated as an approved exception.

Open the 「API 接入」 page in the workbench. Configure a provider, HTTPS base URL, model ID and credentials for each task. Settings apply to the current session. A provider key may cover more than one model if your account grants those permissions. ComicFlow can copy a key between text and vision when the provider and base URL match. Keep the model ID for each use case. A text model can also handle image review only if it accepts image inputs. Image generation requires an image-output model and its supported API. [OpenAI images and vision guide](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat) · [Ark API key permissions](https://console.volcengine.com/ark/region%3Acn-beijing/docs/manage-api-keys)

For optional AI review, preview a PNG, JPEG or WebP and click 「AI 辅助看图」. The selected image and a review prompt are sent after confirmation. Images over 6 MiB are prepared as a compressed local copy before sending. AI suggestions stay separate from the local validation result.

Use 「对白与九图预算」 to count planned files against the nine-image upload limit. For dialogue, import or paste the approved sentence JSON and choose 「预排完整句」. This runs `plan_english_dialogue.py` beside the selected workflow validator and shows candidate groups, word counts, and original dialogue IDs and spans. Candidate groups still need review against shot continuity before production. Both checks run locally.

After checking a complete ZIP, use 「逐格复核」 to select a shot and compare its storyboard sheet, referenced clean plate and slot, production record, and SD2 prompt. The window shows neighboring storyboard thumbnails and action summaries and can step between groups. Drag over either image to zoom into the selected pane. Manual regions are kept per shot until the review window closes. Review is read-only and local.

Use 「资产与返修」 to create or select a local asset database. Register approved originals by asset ID and version. A scan of a new directory can relink a renamed or moved file by exact SHA-256. New production records can use `asset:ID@version` in the reuse ledger. For old records, register the source path printed in the ledger as the original reference. The selected database is used in the workbench validator, or pass `--asset-registry` on the CLI.

In 「返修打包」, enter a shot ID to see related files in the most recently checked ZIP. Select the repaired delivery directory, workflow validator, and a new ZIP path. The workbench validates the directory and ZIP, checks CRC and compares member hashes, then publishes a new file on success. If the original ZIP is available, the report also lists changed, added, and removed members. Approved exceptions tied to another ZIP digest require fresh approval.

---

## 简体中文

### 项目介绍

ComicFlow Validator 是面向 Seedance 2.0 的 Windows 漫剧制片工作台。新建项目可接着做剧本、拆分镜、分析资产、做故事板和提示词，再逐格复核并导出交付 ZIP。已经有原稿、项目或素材时，也能从对应工序开始。

### 怎么减少 Seedance 2.0 抽卡

先核对批准对白、镜头顺序、角色与道具、机位净板和九图预算，再把确认过的素材与提示词提交给 Seedance 2.0。逐格对照找出跳切、素材不一致和状态漂移，再定位到对应图、文字或局部返修，减少可以提前发现的问题导致的反复试生成和整组重做。

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

1. 安装带 Tcl/Tk 的 Python 3.13，再双击 `ComicFlow-Setup.bat` 安装依赖。试用包下载位置、内置样例和操作说明见 [Windows 试用指南](WINDOWS-TRYOUT.md)。
2. 双击 `ComicFlow-Windows.bat`。点「新建项目」会创建 `.cfproject`，点「继续已有项目」可打开已保存的项目或示例 `Examples/SB01.cfproject`。拿到已交付的压缩包，点「验收已有 ZIP」，也可以把 ZIP 拖到启动器上。
3. 点击「开始验收」可检查文件完整性。需要严格验收时，先选择可信工作流的故事板校验脚本。主窗口会记住该路径，也可通过环境变量 `COMICFLOW_STORYBOARD_VALIDATOR` 预填。
4. 在「验收结果」点选一条记录，查看可定位的组、镜号和对应文件。可在下方切换组内文件，也可打开「完整报告」看原始输出。预览与验收使用同一份临时 ZIP 副本，关闭窗口即清理，全程在本机工作。
5. 点「逐格复核」，按镜号查看故事板整图、对应的彩色净板和局部号，以及同镜的生产记录与 SD2 提示词。下方显示前后镜的缩略图和动作摘要，可点「上一镜／下一镜」跨组切换。拖动框选图片中的格子可放大对照。前后镜有框选时显示所选格，否则标为整板。框选范围按镜号保留到本次复核窗口关闭。复核不会改写交付包。

开发验收可在 Windows 安装依赖后运行 `python tests/windows_smoke.py`。它用合成包测试双击启动、传入 ZIP 和通过 Windows Shell 打开 `.cfproject`，并实际操作 Tk 窗口。验证资源管理器的鼠标拖放时，可将一个 ZIP 拖到 `ComicFlow-Windows.bat` 上并检查窗口里的路径。

### 漫剧制片工作台

| 一级页面 | 功能 |
| --- | --- |
| 故事板制作 | 剧本创作、分镜拆分、资产分析、资产及故事板生图、提示词、服装与动作参考、排版与交接、单组 ZIP 交付。 |
| 检查验收 | 图片像素、比例和文件大小、ZIP 完整性与规则验收、逐格核图、跨页和跨组镜头对照、资产返修。 |
| API 接入 | 分用途配置文本、审图和生图。 |

同一项目可接续「剧本创作 → 分镜拆分 → 资产分析」。剧本编辑器可把选定的原稿写入新项目或作为已有项目中的剧本版本。镜头清单与已采纳的 AI 分镜都可进入下一步，资产分析带入该版本的原文与已保存镜头。从各页入口仍可打开已有项目或从本地导入稿件。

服装设计内置 23 套 CC0 服装参考，可按现代日常、通勤与职业、婚礼与宴会、古装与民国、动作与幻想筛选，也可导入有权使用的图。动作设计通过在线 3D 导演台摆姿和机位，将取景图导入 ComicFlow。两种入口都会把选定的本地参考带入生图预览。 [PoseWear](https://posewear.pages.dev/#costume) · [Shisei](https://github.com/wquguru/shisei) · [3D 导演台](https://github.com/xiaozangao/3d-director-desk)

### Seedance 2.0 单组制片

「中文影片制作」与「英文影片制作」专为字节跳动 Seedance 2.0 成片交付适配。工作台按该流程准备故事板、PNG 参考素材、SD2 提示词和交付 ZIP。使用其他视频模型时，素材上限、提示词结构和镜头衔接可能需要重新调整，匹配度可能较低。导出的素材和提示词需在 Seedance 2.0 服务中提交。 [字节跳动 Seedance 2.0](https://seed.bytedance.com/seedance2_0) · [火山方舟视频生成说明](https://console.volcengine.com/ark/region%3Acn-beijing/docs/video-generation-tutorial)

在主窗口选择当前工作流的校验脚本，再进入「单组制片」。新建项目后，导入带版本的批准剧本、该组对白和 PNG。按镜头绑定剧本源段、净板文件和对白 ID，填写制片记录与成片要求。镜头移动时，来源 ID 保持稳定，播放镜号与净板局部号按新顺序生成。

保存项目时保留同名的 `.assets` 素材目录与 `.assets.sqlite3` 登记文件，方便后续恢复和复验。调整顺序后先按新格号检查实际图片，再打开「生成逐格复核预览」。确认画面后运行「验收并导出 ZIP」，两份 TXT 和 README 由同一份镜头清单生成。选择原包可比对成员变化。制片、复核和打包在本地运行。

#### 文本制片

在单组制片点「对白与分镜起草」。本地可以预排批准整句和九图预算。对白 JSON 每条保留 `id`、`speaker` 和完整原文 `text`。同一 ID 有多句时，可填 `sentence_ends`，例如对白 `Hold here. Stay clear.` 用 `[11, 22]` 划分两句。终点为零起点、不包含终点的字符位置，空格可放在相邻两段任一侧。选择本组使用的候选，再在镜头中分配实际发声区间。跨组续说可载入上一组项目核对退出状态。首组仍有同一 ID 的余文时，预览和 ZIP 中也会生成 `待制作分镜.txt`。

「文本模型与历史」可选择已有服务预设或自定义 OpenAI 兼容接口。填写支持文本输出的模型 ID 和 API Key，选择批准剧本行段后查看即将发送的内容。确认后调用该服务。三种任务提供分镜、状态交接和 SD2 动作与声音建议。分镜建议采纳后先核对对白、人数、设备状态与净板。SD2 建议只写入镜头的成片动作和声音栏。交接建议由用户确认并录入。候选及编辑版本保存在本地项目，API Key 只在本次软件运行期间使用。

#### API 设置

打开一级页面「API 接入」，按用途分别选择服务商、HTTPS 基础地址、模型 ID 和凭证。本次运行内可在对应工具中直接使用这些设置，只有确认提交时才会向服务商发送任务。

| 用途 | 模型能力 | 从哪里发起 |
| --- | --- | --- |
| 文本创作 | 接收文本并输出文本。当前工具基于批准剧本起草分镜、SD2 提示词和交接建议。 | 项目中的「对白与分镜起草」或「写提示词」 |
| AI 审图 | 接收选定图片并输出文字审核建议。 | ZIP 文件预览中的「AI 辅助看图」，建议供人工复核 |
| 图像生成 | 输出图像。参考图、局部编辑和张数限制由所选预设和模型决定。 | 项目中的「图像制片」 |

同一个 API Key 能否覆盖多个模型，取决于服务商、账号和权限。文本创作与 AI 审图的服务商和 HTTPS 基础地址相同时，可在设置中主动复制 Key，各用途仍分别填写模型 ID。文本模型支持图片输入时，才可同时用于 AI 审图。图像生成使用其对应的图像模型与接口；账号许可复用 Key 时，可以在该分类手动填写。凭证只在本次软件运行期间保留。 [火山方舟 API Key 权限](https://console.volcengine.com/ark/region%3Acn-beijing/docs/manage-api-keys) · [OpenAI 图像理解与生成](https://developers.openai.com/api/docs/guides/images-vision?api-mode=chat)

#### 图像制片

「图像制片」提供文生图、参考图生图和局部编辑。按服务商和当前预设选择可用模式。用途包括角色、道具 / HUD、场景、故事板和净板。生成净板时，选择已有批准故事板和目标镜头，软件将该镜的机位信息和组内局部号加入提示。「预览本次发送」在本机显示完整提示词、接口地址和每张参考图的批准版本。确认提交时才需要密钥，并使用所选服务的额度。

| 预设 | 接口 |
| --- | --- |
| 火山方舟 Seedream、OpenAI GPT Image、Google Gemini、阿里云百炼千问和万相、xAI Grok Imagine、OpenRouter | 文生图、批准参考图生图、局部编辑。允许的参考图张数按当前预设显示。填写其他模型 ID 前核对其实际能力。 |
| 智谱 CogView、百度千帆、硅基流动 | 当前预设提供文生图。 |
| 腾讯云混元 | 文生图和单参考图异步任务。输入 SecretId 和 SecretKey，重开项目后可用保存的任务编号查询。 |
| 自定义 OpenAI Images 兼容 | 适用于支持相应 Images 协议的地址。 |

百炼填区域工作空间的 API 基础地址，末尾到 `/api/v1`。火山方舟可填写图像模型 ID 或开通的推理接入点。预设已做模拟协议测试，真实账号、模型权限、地区和实际画质需用各自的 Key 实测。密钥只在本次运行期间使用。

异步提交、结果和参考图的 SHA-256 存在项目内。返回结果放在同名的 `.candidates` 目录，确认画面、版本与实际核图记录后才加入批准图像。局部编辑先在批准原图和候选图上各框选对应区域，再用批准原图作底合成。软件重新解码合成图并核对选区外像素。若局部需要按尺寸对齐，界面会提示。批准同名修订时保留原图和既有来源，将正式净板绑定指向新版本。出包时只包含批准图和正式制片记录。新任务超时后可按任务编号查询，或先到服务商后台核对受理状态。

### 本地排版与跨组交接

「单组制片」中的「排版与交接」可以给每镜绑定批准的黑白板格和彩色净板。独立图可用整图，现成的同用途合图可框选实际窗口。排版预览会生成单张故事板、净板页、局部号和地点标签，并记录实际像素窗口。可在板格内画人物、敌方或道具运动箭头，成片说明会排除这些辅助标注。按需选择多场景共用净板页，同一页里的不同镜头仍各有独立窗口。软件只等比缩小，不拉伸。遇到无法铺满整板的格数，预览会标出板面余量。

采用排版后，在「复核与交付」可以直接从成品的真实窗口定位本镜和前后镜。插镜、换序或改动绑定后，先重新排版再复核与出包。旧图保留为批准参考，正式文件名和播放编号由实际镜头顺序生成。

「相邻组交接」可载入同集连续的下一组，对照前组末格、后组首格、净板、连续性和批准对白区间。逐格确认两组并确认交接后，可严格验收并导出双组 ZIP。需要下批继续做的镜头可先暂存，保留源镜 ID 和对白原文区间，到下一组接收。最后一组的待制作内容在顶层 `待制作分镜.txt`，并更新 README。

### 资产登记和返修打包

- 打开「资产与返修」，建一个本地 `.sqlite3` 资产登记库，填写批准原图、资产 ID 和版本。对旧包可在「原引用」填写生产记录里的旧路径。新版生产记录可使用 `asset:资产ID@版本`。换电脑时保留登记库，在新素材目录按 SHA-256 找回；同名异图或重新编码的图不会通过直接复用校验。选择过的登记库会供本次运行的验收使用，命令行也可传 `--asset-registry`。
- 返修打包前，可先验收原 ZIP，再输入完整镜号查看故事板、所指向的净板、两份 TXT 和已有 README。修复实际文件后，选择返修目录和一个新的 ZIP 文件名。工具复验目录、ZIP CRC 和逐文件 SHA-256，验证通过后才发布，并列出相对原包修改、新增和删除的文件。界面可保存一份「问题—位置—修复—复验」报告。绑定旧包 SHA-256 的例外需要针对新包重新批准。

常规长对白组确有获批的超六格例外时，直验 ZIP 可加 `--panel-exception 文件.json`，也可在启动器选择该 JSON。填写 `zip_sha256`（最终 ZIP 的小写 SHA-256）、`group`（如 `SB05`）、`panels`（批准的格数，7–12）和 `reason`（单行批准理由）。例外只适用于该 ZIP，该组及该条六格规则。

### 对白与九图预算

点「对白与九图预算」，按单组填写主角、配角、道具/HUD、场景的计划图片张数，再按实际排版确认故事板页数。窗口显示九图预算的剩余量或超量。

英文对白可导入 JSON 或直接粘贴。选好工作流的校验脚本后，点「预排完整句」，程序调用同目录的 `plan_english_dialogue.py`，显示候选组词数、说话人、源对白 ID 和原文区间。每条是一个批准的完整发声句，格式如 `[{"id":"D001","speaker":"角色甲","text":"Hold the door."}]`。跨镜或跨组续说时可使用原有 `start` 和 `end` 字段。候选分组需结合动作承接和镜头内容确认。两项预检均在本机完成。

### 可选 AI 辅助看图

在窗口选择并预览一张 PNG、JPEG 或 WebP，点击「AI 辅助看图」。可选豆包（火山方舟）、千问（阿里云百炼）、Claude、OpenAI、Gemini、Kimi、GLM（智谱）、混元（腾讯云 TokenHub）、千帆（百度智能云）、硅基流动、OpenRouter、Grok 和自定义 OpenAI 兼容接口。

填写支持图片输入的模型 ID 和该服务的 API Key，可按账号地域更换 HTTPS 基础地址。确认后仅发送选中图片和看图提示。超过 6 MiB 的预览图片会先在本机生成压缩副本，发送窗口会标明。Key 只保留在当前运行内存中，模型建议单独展示供人工复核，本地验收结论照常保留。

---

**Project:** ComicFlow Validator  
**Development:** Open Source  
**Platform:** Windows (initial target)
