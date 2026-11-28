"""Bilingual walkthroughs for the storyboard production workspace."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GuideTopic:
    title: tuple[str, str]
    intro: tuple[str, str]
    sections: tuple[tuple[tuple[str, str], tuple[str, str]], ...]


STORYBOARD_TOPICS = {
    "home": GuideTopic(
        ("故事板制作首页", "Storyboard production home"),
        (
            "从一份原稿开始，也可以打开现有分镜，直接进入需要的工序。",
            "Start from a script, or resume an existing shot list at the stage you need.",
        ),
        (
            (("两个练习入口", "Two ways to practice"), (
                "点「从剧本练习」并选一个文件夹，软件会在独立练习目录放好 Approved-Script.txt 和 Local-Reference.png，并打开剧本草稿。核对左侧稿件后可带入分镜。点「从已有分镜练习」会复制示例项目和配套图片，直接打开「批准图像」，可开始浏览素材。两个入口均可离线使用。",
                "Choose Practice from a script and select a folder. The app opens a script draft and writes Approved-Script.txt and Local-Reference.png to a separate practice folder. Review the left draft before taking it into shot planning. Practice from existing shots opens Approved images in a copy of the sample project and its images. Both practice routes work offline.",
            )),
            (("选制作规则", "Choose production rules"), (
                "首页默认选「英文影片制作」。新建前可改选「中文影片制作」。制作规则控制分镜、对白和交付格式，按 Seedance 2.0（SD2）设计。换用其他视频模型时，按目标模型调整画面参考和提示词。界面语言可用「中文 / English」单独切换，已有项目沿用自己的制作规则。",
                "English film production is the starting preset. Choose Chinese film production before creating a group if appropriate. The preset controls shot, dialogue and delivery rules designed for Seedance 2.0 (SD2). Adapt the references and prompts when using another video model. The 中文 / English interface switch is separate. Saved projects retain their production rules.",
            )),
            (("跟着项目走", "Follow a project"), (
                "通过首页的工序入口，从「剧本创作」把稿件带到「分镜拆分」，再进入「资产分析」和图像制作。用本地文件可从任一步开始。任务会在顶部打开页签，窄窗口可从任务下拉找到隐藏页签。遇到不熟悉的操作，可点「本页帮助」，看完用「返回发起页」继续。",
                "Use the home shortcuts to take a script from Script writing to Shot planning, Asset analysis and image production. Local files let you enter at the stage you need. Task tabs open at the top. In a narrow window the task menu lists hidden tabs. Use Help for this page if you get stuck, then Return to originating page to resume.",
            )),
            (("离线与费用", "Offline work and costs"), (
                "手动编辑、导入本地文件、查看预览和打包均可离线。确认提交文本或图像请求会使用所选服务商的 API 额度。已有交付包可点「验收已有 ZIP」直接检查。",
                "Manual editing, local imports, previews and packaging run offline. Confirming a text or image request uses the selected provider’s API quota. To inspect an existing delivery archive, use Validate an existing ZIP.",
            )),
        ),
    ),
    "project": GuideTopic(
        ("新建和打开单组项目", "Create or open a group project"),
        (
            "一个 .cfproject 保存一组故事板的剧本版本、镜头、批准图像登记和制片记录。",
            "A .cfproject records script revisions, shots, approved image registrations and production notes for one storyboard group.",
        ),
        (
            (("从首页进入", "Start on the home page"), (
                "先选「英文影片制作」或「中文影片制作」。点「新建项目」，在可写目录保存 .cfproject，例如 D:\\StoryboardPractice\\SB01.cfproject。要继续编辑，点「继续已有项目」选择 .cfproject。安装包有 Examples/SB01.cfproject 和 Examples/中文制作/SB01.cfproject，也可用教程入口生成练习副本。",
                "Choose the English or Chinese production preset first. Select New project and save a .cfproject in a writable folder, for example D:\\StoryboardPractice\\SB01.cfproject. To continue editing, use Resume saved project and select the .cfproject. The package includes Examples/SB01.cfproject and Examples/中文制作/SB01.cfproject. You can also use the guide to create a practice copy.",
            )),
            (("填写组信息和原稿", "Set the group and script"), (
                "在「项目与组」确认项目名、集次和组号，例如 EP001、SB01。点「导入批准剧本」选用 UTF-8 的 TXT 或 Markdown，再用「查看原文和对白 ID」检查源稿。在「编辑本组批准对白 JSON」中登记已经批准的对白和说话人。点「保存项目」，然后进「镜头清单」。",
                "In Project & group, confirm the project name, episode and group ID, such as EP001 and SB01. Use Import approved script to open a UTF-8 TXT or Markdown file, then review it under View script & dialogue IDs. Record approved dialogue and speakers with Edit approved dialogue JSON for this group. Select Save project and continue to Shot list.",
            )),
            (("复制或找不到项目", "Moving or locating a project"), (
                "移动项目时把同名的 .assets 文件夹和已存在的 .candidates 文件夹、.assets.sqlite3 一起复制。打开窗口默认只显示 .cfproject。手里是原稿或 PNG 时，新建项目后从对应工序导入。手里是 ZIP 时，从首页「验收已有 ZIP」进入。",
                "When moving a project, copy its matching .assets folder, plus its .candidates folder and .assets.sqlite3 file if present. The project picker displays .cfproject files. If you have scripts or PNGs, create a project and import them at the relevant stage. For a ZIP, select Validate an existing ZIP on the home page.",
            )),
        ),
    ),
    "script": GuideTopic(
        ("剧本创作", "Script writing"),
        (
            "从构思起稿，或直接采用已经审核的本地剧本。",
            "Draft a script from a brief, or bring in a local script you have already reviewed.",
        ),
        (
            (("输入剧本", "Provide the script"), (
                "从「故事板制作」打开「剧本创作」。填写「稿件标题」，把构思或正文放进左侧，也可点「导入 TXT / Markdown」。只有创作要求时，先手工补成完整剧本，或在右侧起草候选。",
                "Open Script writing from Storyboard production. Enter a Document title, then paste the brief or script in the left pane, or use Open TXT / Markdown. If you have a brief, turn it into a full script yourself or draft a candidate in the right pane.",
            )),
            (("本地编辑或用模型起草", "Edit locally or draft with a model"), (
                "本地编辑后可「另存左侧稿件」。使用模型时先在「API 接入」配置文本模型，再选「文本模型」并点「预览发送内容」。检查规则和发送内容后才点「调用模型写草稿」并确认，调用使用服务商额度。右侧候选可编辑或另存。",
                "For local work, use Save left draft as. To use AI, configure a text model in API connections, select it under Text model and use Preview request. Review the rules and payload, then confirm Draft with AI to use the provider’s quota. You can edit or export the candidate in the right pane.",
            )),
            (("带入分镜", "Bring the script into shot planning"), (
                "核对剧情、角色、对白和原语言后，点「用左侧稿件拆分镜」或「用右侧候选拆分镜」。选「新建项目并拆分镜」或「加入已有项目」并确认，选定稿件会作为来源版本带到镜头清单。",
                "Review the plot, cast, dialogue and original language. Select Plan shots with left draft or Plan shots with right candidate. Choose Create project and plan shots or Add to an existing project and confirm. The selected manuscript becomes a source revision in the shot list.",
            )),
            (("稿件预览不对时", "If the draft looks wrong"), (
                "回到原来一侧修改，选正确的采用按钮。已有批准剧本时也可直接从「分镜拆分」导入。调用失败先核对服务商、模型 ID 和密钥，再决定是否重发。",
                "Edit the correct pane and choose the corresponding handoff button. An approved script can also go straight into Shot planning. After a failed model call, check the provider, model ID and key before deciding whether to retry.",
            )),
        ),
    ),
    "shots": GuideTopic(
        ("分镜拆分和镜头清单", "Shot planning and shot list"),
        (
            "给每镜安排一个主要叙事目的，并保留它与批准剧本和对白的对应关系。",
            "Give every shot a clear storytelling purpose and link it to approved script and dialogue.",
        ),
        (
            (("从当前项目或本地剧本开始", "Use the current project or a local script"), (
                "从首页点「分镜拆分」，选择当前项目或打开 .cfproject。新组可在本页点「导入批准剧本」，或从「剧本创作」带入已核对稿件。使用「插入镜头」「编辑镜头」，选择对应的剧本版本和源段位置，填写动作起止、景别、机位、入画人物和对白 ID，点「应用镜头更改」。",
                "Select Shot planning on the home page and use the current project or open a .cfproject. For a new group, select Import approved script or bring in a reviewed draft from Script writing. Use Insert shot or Edit shot, choose the script revision and source range, then record action, framing, camera angle, visible cast and dialogue IDs. Select Apply shot changes.",
            )),
            (("逐镜核对", "Review each cut"), (
                "保留批准原对白和说话人。跨镜续说按原句范围分配。检查相邻镜的景别、机位、视线和动作连接，注意同景别同机位的重复跳切。移动或插入镜头后按播放顺序重查格号和净板局部号，稳定源 ID 用来追溯同一镜。",
                "Keep approved dialogue and speakers. For dialogue across shots, assign spans from the original line. Check framing, angle, eyelines and action across cuts, including jump cuts caused by repeating both the framing and angle. After moving or inserting shots, recheck panel and clean-plate crop numbers in playback order. Stable source IDs identify the same shot through revisions.",
            )),
            (("下一步", "Continue to assets"), (
                "手工拆镜可离线操作。想请模型先排一版，点「AI 拆分镜」，核对候选再采纳。镜头就绪后点「下一步：分析资产」。按钮提示缺少信息时，先确认每镜都绑定批准剧本和源段。多个剧本版本按版本逐次分析。",
                "Manual shot planning works offline. For model suggestions, choose Plan shots with AI, then review the candidate before applying it. Once the shots are ready, select Next: analyze assets. If the app reports missing inputs, check each shot’s approved script and source range. Analyze one revision at a time for groups with multiple script revisions.",
            )),
        ),
    ),
    "drafts": GuideTopic(
        ("对白预排与分镜起草", "Dialogue planning and shot drafts"),
        (
            "先按批准对白和交付预算排组，再决定是否调用模型起草镜头。",
            "Plan groups around approved dialogue and the delivery budget, then decide if you want shot suggestions from a model.",
        ),
        (
            (("准备本组对白", "Prepare group dialogue"), (
                "在「项目与组」导入批准对白，给每句记录 ID、说话人和原句。需要自然停顿时，在对白 JSON 填 sentence_ends。「镜头清单」的「AI 拆分镜」打开起草工具，也可从「对白与九图预算」进入对白预排。",
                "In Project & group, import approved dialogue with IDs, speakers and original lines. To mark natural breaks, use sentence_ends in the dialogue JSON. Plan shots with AI in Shot list opens the drafting tools. Dialogue & image budget also opens dialogue planning.",
            )),
            (("先预排再采用", "Plan before adopting"), (
                "英文组打开「对白与九图预排」，中文组用「中文对白预排」。按当前规则检查对白范围和图片预算，选中一组后核对跨镜范围与断点，再点「采用所选对白组」。有上一组交接文件时，可用「载入上一组交接」带入已确认的状态。",
                "Use Dialogue & image budget for an English group or Plan Chinese dialogue for a Chinese group. Check spoken spans and the image budget under the active rules. Select a group, review any lines split across shots, then choose Use selected dialogue group. Use Load previous handoff to bring in approved continuity from the preceding group.",
            )),
            (("预览并核对模型结果", "Preview and review model output"), (
                "在「文本模型与历史」选模式、模型和剧本行段，先点「查看发送内容」。确认「调用模型起草」会用服务商额度。逐项核对右侧候选的原稿、镜头动作和对白，必要时「保存编辑为新版本」。勾选可用建议后点「采纳已选建议」，回到镜头清单再复核。",
                "In Text model & history, choose the task, model and script lines, then select Preview request. Confirming Generate draft uses the provider’s quota. Check the candidate against the script, shot actions and dialogue. Use Save revision after editing if needed. Select usable suggestions, choose Apply selected suggestions and check them again in Shot list.",
            )),
            (("按钮不可用时", "If a control is unavailable"), (
                "先检查批准剧本、有效起止行和对白 ID。要调用模型，在「API 接入」给文本任务选支持所需输出格式的模型并填本次密钥。无 API 时仍可手工预排和拆镜。",
                "Check the approved script, line range and dialogue IDs. To make a call, set up a text model in API connections with the required output format and a session key. Manual dialogue planning and shot editing remain available offline.",
            )),
        ),
    ),
    "inventory": GuideTopic(
        ("资产分析", "Asset analysis"),
        (
            "从原稿和镜头整理本组实际入画的角色、场景、道具和状态变化。",
            "Build a list of the characters, locations, props and state changes the group actually shows.",
        ),
        (
            (("选分析范围", "Choose the scope"), (
                "从「镜头清单」点「下一步：分析资产」，软件会带入这一版原稿和引用它的镜头。想独立分析时，从首页打开「资产分析」，在左侧粘贴剧本或「导入 TXT / Markdown」。已有清单可点「导入本地资产清单」。",
                "Select Next: analyze assets in Shot list to bring in the script revision and the shots that refer to it. For a standalone analysis, open Asset analysis on the home page and paste a script or use Open TXT / Markdown. Use Import local asset report if you already have a list.",
            )),
            (("核对清单", "Review the asset list"), (
                "按角色、场景、道具整理资产，注明出现镜头、所需视角、服装和持物状态。确认可以复用的批准原图，记下缺图或换装等变化。可手填右侧清单，或选文本模型并先「预览发送内容」，再确认「调用模型分析资产」。只有提交模型请求会使用额度。",
                "Group entries by character, set and prop. Note their shots, required views, wardrobe and prop states. Identify reusable approved originals, missing images and changes such as a new outfit. Fill the right-hand list yourself or use Preview request before confirming Analyze with AI. Only the model request uses quota.",
            )),
            (("带入生图", "Carry the list into image production"), (
                "核对后可「另存右侧候选」保留文本。点「制作资产图」把清单带到项目的图像工序，生图前按所需资产分任务，逐张核对参考图和本次提示词。清单与现有镜头不符时，先回「镜头清单」处理原稿版本或范围。",
                "Use Save right candidate as to keep a text copy. Select Make asset images to carry the list into the project’s image stage. Before generating, make a job for each needed asset and check its references and prompt. If the list and current shots disagree, resolve the script revision or shot range first.",
            )),
        ),
    ),
    "generate_assets": GuideTopic(
        ("资产图生成", "Asset image generation"),
        (
            "为角色、场景、道具或净板创建生图任务。核对候选后，才将合格图像登记到项目。",
            "Create jobs for characters, sets, props or clean plates. Review each candidate before registering it in the project.",
        ),
        (
            (("选择项目和输入", "Choose the project and inputs"), (
                "在首页点「资产图生成」，选择当前或已有 .cfproject。可从「资产分析」把清单带进来，也可直接写本次需求。先确认「API 接入」的图像生成模型支持所选模式，再点「载入 API 接入设置」。有批准本地图片时，可直接用「批准图像」导入 PNG。",
                "Open Asset image generation and choose the current project or an existing .cfproject. Bring in asset analysis or write notes for this job. Set up an image generation model that supports the mode in API connections, then use Load API connection. If you already have an approved image, you can import the PNG under Approved images.",
            )),
            (("确认发送", "Confirm the request"), (
                "在「新建生图任务」选用途和「文生图」「参考图生图」或「局部编辑」。需要参考时点「按图选择参考」，核对身份和画面状态。局部编辑可「框选返修区域」。先看「预览本次发送」里的接收地址、模型、锁定规则、提示词和图片，再点「确认并提交生图」。服务商按其规则计费。",
                "In New image job, set Image purpose and choose Text to image, Reference to image or Local edit. Use Choose references visually to review identity and image state when adding references. For local edits, use Select repair area. Check destination, model, locked rules, prompt and images under Preview request, then select Confirm & generate. The provider bills the request under its own rules.",
            )),
            (("复核与登记", "Review and register the result"), (
                "到「候选与任务」查看结果。用「查看候选与批准参考」比较原图与候选，检查脸、装备、持物和场景细节。对局部返修可先「生成局部合成」。选合格图后点「批准候选图」并「确认批准」。批准资产可供后续故事板参考和组内交付。",
                "Open Candidates & jobs to review the result. Compare the candidate with approved references for faces, equipment, held objects and set details. For a local repair, preview a local composite first if needed. Use Approve candidate and Confirm approval for acceptable images. The approved asset is available for storyboard references and group delivery.",
            )),
            (("任务还在运行时", "If a job is still running"), (
                "可从「任务中心」找回运行中的任务页签，或在「候选与任务」点「查询所选任务」。先看已有任务状态再重试，避免重复提交。模式不可选时，检查服务商及模型支持的图像能力。",
                "Return to a running job from the job center, or use Check selected job in Candidates & jobs. Check the existing job’s status before retrying to avoid a duplicate submission. If a mode is unavailable, check whether the chosen provider and model support it.",
            )),
        ),
    ),
    "generate_board": GuideTopic(
        ("故事板图生成", "Storyboard generation"),
        (
            "用当前组镜头清单和参考图生成故事板候选，逐格核对后再进入排版和交付。",
            "Generate a storyboard candidate from the group’s shot list and references, then review each panel before layout and delivery.",
        ),
        (
            (("准备镜头和参考", "Prepare shots and references"), (
                "点首页「故事板图生成」，选择当前项目。先让镜头编号、动作、对白与入画人物形成稳定顺序。参考图只选本组实际使用的角色、道具和场景。黑白故事板控制构图动作，批准彩色资产控制角色与场景颜色。",
                "Choose Storyboard generation on the home page and select the project. Set the shot order and check action, dialogue and visible cast first. Use character, prop and set references for what actually appears in the group. Black-and-white boards guide composition and action. Approved color assets guide the finished palette.",
            )),
            (("预览和提交", "Preview and submit"), (
                "在「新建生图任务」确认类别为「故事板」，载入图像接口，选参考并补充本次要求。先预览模型、接收地址、锁定规则、提示词和图片，再确认提交，使用所选服务商额度。",
                "In New image job, check that the category is Storyboard. Load the image API connection, select references and add job notes. Preview the model, destination, locked rules, prompt and images before confirming a request against the provider’s quota.",
            )),
            (("检查画面并进入排版", "Review visuals and move to layout"), (
                "在「候选与任务」按镜号核对每一格，确认景别、机位、走位、实际可见人数量及板格顺序，合格后用「批准候选图」登记。手里已有批准图，可在「批准图像」导入 PNG。到「排版与交接」绑定到对应镜头并生成排版预览。",
                "In Candidates & jobs, check framing, camera angle, blocking, visible cast and panel order against each shot ID. Register accepted results with Approve candidate. If you have approved PNGs, import them under Approved images. Continue in Layout & handoff to bind images to shots and preview the layout.",
            )),
            (("画面不连贯时", "If panels do not match"), (
                "先对照批准参考和镜头清单定位错误。可重选参考或返修目标格，再复核对应动作与净板。准备好画面后再进入「故事板组打包交付」。",
                "Use approved references and the shot list to locate the mismatch. Change the references or revise the affected panel, then review its action and clean plate again. Once the visuals are ready, continue to Package storyboard group.",
            )),
        ),
    ),
    "prompts": GuideTopic(
        ("Seedance 2.0 提示词生成", "Seedance 2.0 prompt drafting"),
        (
            "按当前制作规则整理成片需要的镜头、动作、人物、背景、声音和限制。",
            "Prepare each shot’s action, cast, setting, sound and constraints under the active production rules.",
        ),
        (
            (("进入提示词工序", "Open prompt drafting"), (
                "从首页点「提示词生成」，选择单组项目。用「导入提示词 TXT / Markdown」带入现有公共说明，或沿用编辑区的字段标题填写成片环境与约束。镜头独有的动作、人物与声音回「镜头清单」按镜编辑。",
                "Select Prompt drafting on the home page and choose a group project. Use Import prompt TXT / Markdown for existing shared notes, or enter the setting and constraints under the existing editor labels. Edit shot-specific action, visible characters and sound in Shot list.",
            )),
            (("从本组信息起草", "Draft from the current group"), (
                "离线可以手写。用模型时点「调用模型起草提示词」，选文本模型和目标镜头，先「查看发送内容」。锁定规则、源段和已选状态会显示在预览里。确认调用才使用额度。核对候选，选取可用项后采纳。",
                "Write prompts locally, or choose Draft prompts with a model, select a text model and target shot, then use Preview request. The preview shows the locked instructions, script excerpt and selected state. Confirming the model call uses quota. Review the candidate and apply the suggestions you want.",
            )),
            (("对照画面与文字", "Check against visuals and text"), (
                "确认每镜提示词与板格和净板对应。只保留实际入画的人物与数量、批准对白原文、关键动作和声音。把净板加工、资产来源和审计记录留在制片记录里。核对后「保存项目」，再去「故事板组打包交付」检查最终文本。",
                "Check each prompt against its panel and clean plate. Include the visible cast, exact counts, approved dialogue, key action and sound. Keep clean-plate processing, asset provenance and audit details in the production notes. Save the project, then review final text under Package storyboard group.",
            )),
        ),
    ),
    "assets": GuideTopic(
        ("批准图像", "Approved images"),
        (
            "把已核准的 PNG 登记到当前组，供故事板绑定、制片和交付。",
            "Register approved PNGs for storyboard binding, production and delivery in the current group.",
        ),
        (
            (("打开登记页", "Open the image register"), (
                "从首页「批准图像」进入项目。点「导入批准 PNG」选本地图片，再登记对应的文件名、范围与版本。有已登记原图时可点「从资产登记库导入」。普通参考图和视频在「打开素材库」里导入和分类。",
                "Select Approved images on the home page and choose a project. Use Import approved PNG to register a local image with its filename, scope and revision. Use Import from registry for an already registered original. Use Open media library to import and sort ordinary reference images and videos.",
            )),
            (("核对图片和用途", "Check the image and its role"), (
                "用「打开图片」查看人物身份、服装、道具、场景状态和有效清晰度。登记后到「镜头清单」或「排版与交接」指定故事板板格和净板对应关系。保存项目后可在其他工序选择已批准参考。",
                "Use Open image to check identity, costume, props, set state and usable sharpness. Once registered, map panels and clean plates in Shot list or Layout & handoff. Save the project so other stages can select your approved references.",
            )),
            (("更换或找回图片", "Replace or recover an image"), (
                "准备替换正式图时先核对新图、来源和受影响镜头，重查对应文字和排版。路径变动时确认 .cfproject 旁同名 .assets 文件夹是否完整，查看预览有无定位提示。普通导入的素材可在素材预览里重新定位。",
                "Before replacing an approved delivery image, check the new image, provenance and affected shots, then review their text and layout. If a path moved, check the matching .assets folder next to the .cfproject and look for a preview status. Ordinary imported media can be relinked in its preview.",
            )),
        ),
    ),
    "media": GuideTopic(
        ("项目素材库", "Project media library"),
        (
            "用方形卡片找图或视频，按人物、场景和道具整理，再打开原比例预览。",
            "Find images and videos on square cards, organize them by character, set or prop, and preview them at their original aspect ratio.",
        ),
        (
            (("打开和导入", "Open and import"), (
                "在「批准图像」点「打开素材库」，也可从生图任务点「查看项目素材」。点「导入素材」多选本地图片或视频。选择「类别」「媒体」筛选并用「卡片大小」放大卡片。",
                "Select Open media library in Approved images, or Browse project media from an image job. Use Import media to select local images and videos. Filter by Category and Media type, then adjust Card size to enlarge the cards.",
            )),
            (("整理和选择", "Sort and select"), (
                "点选素材，在底部选「人物」「场景」或「道具」，点「设置类别」。双击卡片或点「查看大图／视频」看细节。在「按图选择参考」里选已批准图像，再点「使用所选素材」带回生图任务。提交前看发送预览。",
                "Select media and choose Characters, Scenes or Props at the bottom, then use Set category. Double-click a card or select Open preview to inspect it. In Choose references visually, select approved images and use Use selection to return them to the image job. Check the request preview before submitting.",
            )),
            (("找不到素材时", "If an item is missing"), (
                "先放宽「类别」与「媒体」筛选，查看「待分类」。遇到文件移动可从素材预览定位原件。要用于正式图像绑定或交付的本地原图，请回「批准图像」点「导入批准 PNG」。",
                "Clear the Category and Media type filters and check Unclassified. If a file moved, locate the original from its preview. For a local original needed in a storyboard binding or delivery, go to Approved images and use Import approved PNG.",
            )),
        ),
    ),
    "media_preview": GuideTopic(
        ("素材大图与视频预览", "Image and video preview"),
        (
            "用原比例预览核对细节。视频可拖时间轴找到适合的参考画面。",
            "Inspect details at the original aspect ratio. Drag the video timeline to find a useful reference frame.",
        ),
        (
            (("放大图片", "Enlarge an image"), (
                "在素材库双击卡片或点「查看大图／视频」。图片可「适合窗口」「放大」「缩小」，放大时拖动画面看清脸、道具和衣着。用「上一项」「下一项」比较当前筛选里的相邻素材。",
                "Double-click a card or select Open preview in the media library. Use Fit to window, Zoom in or Zoom out. Drag the enlarged image to check faces, props and clothing. Use Previous and Next to compare adjacent items in the current filter.",
            )),
            (("检查视频", "Review a video"), (
                "点「播放」或拖动时间轴，软件内预览静音。合适的帧可「设为封面」以便回到素材库定位。要听声音，用「用播放器打开原视频」。结束时点「返回」可继续浏览当前筛选。",
                "Use Play or drag the timeline. In-app video preview is silent. Set as cover makes the current frame easier to recognize in the library. To hear the audio, use Open original in player. Select Back to return to the current filter.",
            )),
            (("无法读取时", "If playback or preview fails"), (
                "如果素材路径失效，点「重新定位素材」找回原文件。视频不出画面时，先核对文件能否在本地播放器完整播放。预览、设封面和本地播放均可离线操作。",
                "Use Relink source if the file path changed. If a video has no preview, check that the original plays through in your local player. Previewing, setting covers and local playback all work offline.",
            )),
        ),
    ),
    "costume": GuideTopic(
        ("角色服装设计", "Costume design"),
        (
            "挑选或导入服装参考，将选中的图带到资产图生成。",
            "Choose or import an outfit reference and carry it into asset image generation.",
        ),
        (
            (("选择参考图", "Choose a reference"), (
                "从首页打开「角色服装设计」，用「服装分类」浏览，或按名称、编号搜索。点击方卡后检查轮廓、材质、颜色和配件。已有定稿可以点「导入本地参考图」。",
                "Open Costume design and use Costume category to browse, or search by name or ID. Select a card and check its silhouette, materials, colors and accessories. Use Import local reference for an outfit you already approved.",
            )),
            (("带入角色生图", "Send to character image generation"), (
                "点「使用参考图进入生图」并选择目标项目。在生图任务确认类别、角色身份参考、着装状态和补充要求。先看发送预览，确认提交时才会使用图像服务额度。",
                "Select Use reference in image generation and choose the project. In the image job, check the category, character identity references, wardrobe state and job notes. Preview the payload first. Image quota is used when you confirm submission.",
            )),
            (("复核生成结果", "Review the generated image"), (
                "在候选里对照服装参考和批准角色，检查脸、发型、衣着与识别装备。合格后批准候选，供故事板参考。如果只需要做选型，可以停在本地预览。",
                "Compare the candidate with the outfit reference and approved character. Check face, hair, costume and identifying equipment. Approve a satisfactory candidate for use as a storyboard reference. You can stop at the local preview if you only need to choose a costume.",
            )),
        ),
    ),
    "action_sequence": GuideTopic(
        ("人物动作编排", "Action sequencing"),
        (
            "用动作卡安排节拍、镜头和前后状态，确认后再带入正式分镜。",
            "Arrange beats, shots and continuity with action cards, then review them before sending them to formal shots.",
        ),
        (
            (("打开当前组", "Open the current group"), (
                "从首页「人物动作编排」选择 .cfproject。可点「浏览动作卡」「对话与站位」，或用「导入动作卡」恢复卡片 JSON。可从内置 3D 导演台送回路线点，也可用「导入 3D 导演台工程」从已有工程提取路线参考。",
                "Open Action sequencing and select a .cfproject. Choose Browse action cards or Dialogue & blocking, or use Import cards to load card JSON. Send motion paths from the built-in 3D Director Desk or use Import 3D Director project to extract paths from an existing project.",
            )),
            (("排动作和看格子", "Arrange beats and inspect panels"), (
                "双击卡片完善人物、动作起止、方向、持物与目标镜号。拖动卡片安排先后，在「预演格」切换 12 格或 15 格。用「前后格对照」核对支撑、位置、动作结果和相邻人物状态，然后点「保存动作编排」。",
                "Double-click a card to refine its actor, start and end actions, direction, props and target shot. Drag cards to reorder, then use the 12- or 15-panel Preview panels tab. Compare adjacent panels to check support, position, action outcomes and character continuity. Select Save sequence.",
            )),
            (("应用或另存", "Apply or export"), (
                "对要采用的卡点「带入正式分镜」，按提示核对对应镜号。新增镜头前先导入批准剧本，完成后回「镜头清单」核对源段和对白。要单独交接草案可用「导出动作卡」。卡片编辑和预演均可离线。",
                "Select the cards you want and choose Send to formal shots, then review the target shots. Import an approved script before adding shots. Review source ranges and dialogue again in Shot list. Use Export cards for a separate draft handoff. Card editing and previews work offline.",
            )),
        ),
    ),
    "action_gallery": GuideTopic(
        ("动作预设图库", "Action preset gallery"),
        (
            "先看封面和三个动作阶段，选出能承接当前镜头的预设。",
            "Choose a preset using its cover and three movement stages, checking how it fits the neighboring shots.",
        ),
        (
            (("浏览类别", "Browse the categories"), (
                "在「人物动作编排」点「浏览动作卡」，选「类别」，点击封面查看起始、关键变化和结束。比如日常交流可点「对话与站位」，查看双人或三人的构图和轴线。",
                "In Action sequencing, choose Browse action cards. Select a Category and click a cover to inspect the start, key beat and end. For everyday conversation, use Dialogue blocking to compare compositions and action axes for two or three people.",
            )),
            (("加入编排", "Add to the sequence"), (
                "选择适合的卡，点「加入动作编排」。回到列表把示例人物和道具换成本组实际资产，核对动作持续和结束位置，再看「预演格」。如果只是浏览，点「返回编排」继续原来的工作。",
                "Choose a card and select Add to sequence. In the list, replace its sample cast and props with the group’s assets, check how the action continues and where it ends, then inspect Preview panels. Use Back to sequence to resume the original task after browsing.",
            )),
            (("预览缺失时", "If an illustration is missing"), (
                "可先切换同类卡确认显示是否正常。预设的图用于离线参考。需要项目对应的形象时，可在动作卡编辑区关联本组已经批准的参考图。",
                "Try another card in the same category to check the display. Preset art is available as an offline reference. To use your project’s characters, link an approved group image in the action card editor.",
            )),
        ),
    ),
    "action_preview": GuideTopic(
        ("动作卡大图", "Enlarged action card"),
        (
            "对照一张卡的三个阶段，检查姿势和方向如何变化。",
            "Compare the three stages of a card to see how pose and direction change.",
        ),
        (
            (("从阶段图放大", "Enlarge a stage"), (
                "在「动作预设图库」选卡，再点击要查看的阶段图。底部可切「起始」「关键变化」「结束」，依次检查人物朝向、支撑脚、持物和结束位置。",
                "Choose a card in Action preset gallery and select a stage image to enlarge it. Switch between Start, Key beat and End at the bottom. Check orientation, weight-bearing foot, held objects and final position.",
            )),
            (("回到原任务", "Return to the original task"), (
                "点「返回图库」继续选择，原卡仍可继续查看。要采用时，在图库点「加入动作编排」，再按角色和镜头需要调整。项目内的多张卡连续性在「前后格对照」检查。",
                "Choose Back to gallery to continue with the same card. To use it, select Add to sequence and adjust it to the group’s characters and shots. Check continuity between separate cards with Compare adjacent panels.",
            )),
        ),
    ),
    "dialogue": GuideTopic(
        ("日常表演 · 对话与站位", "Everyday performance · Dialogue blocking"),
        (
            "用站位图和两张机位示意，排双人对话、过肩正反打和三人对话。",
            "Use a blocking plan and two camera views to stage two-person dialogue, over-the-shoulder reverses or a three-person conversation.",
        ),
        (
            (("选择站位和取景", "Choose blocking and framing"), (
                "在「人物动作编排」点「对话与站位」。选择「双人中景同框」「过肩正反打」或「三人三角站位」。查看「俯视站位」「镜头 1」「镜头 2」，可点「放大」确认演员方位、视线、遮挡与镜头轴线。",
                "In Action sequencing, select Dialogue & blocking. Choose Medium two-shot, Over-shoulder reverse or Three-person triangle. Review Overhead map, Shot 1 and Shot 2. Use Enlarge to check actor positions, eyelines, occlusion and the action axis.",
            )),
            (("映射角色和镜头", "Map actors and shots"), (
                "在「对应本组人物」将 A、B、C 换成实际角色。在「应用到」选择要修改的镜头或创建卡片草稿，点「预览应用内容」。应用到已有镜头时，先核对景别、机位、位置和走位，再点「确认应用」。现有对白仍以批准源句为准。",
                "Under Map the cast, assign the actual characters to A, B and C as needed. Under Apply to, choose an existing shot or create a draft card, then select Preview changes. Review framing, camera angle, position and blocking before choosing Apply to update an existing shot. Approved lines remain the dialogue source.",
            )),
            (("应用前的检查", "Checks before applying"), (
                "如果提示说话者不匹配，回镜头清单核对白 ID 和批准说话人，再调整角色对应关系。也可先存为卡片草稿，回编排核对前后格。站位与示意图可离线使用。",
                "If the speaker does not match, check the dialogue ID and approved speaker in Shot list, then correct the cast mapping. You can also use a draft card and review nearby panels in the sequence. Blocking and its illustrations are available offline.",
            )),
        ),
    ),
    "pose": GuideTopic(
        ("角色动作设计", "Character pose design"),
        (
            "用自备姿态图或导演台静帧，给角色生图提供构图和动作参考。",
            "Use a local pose image or a frame from the Director Desk as a character image reference.",
        ),
        (
            (("选择姿态来源", "Choose a pose source"), (
                "从首页点「角色动作设计」。已有批准姿态图时点「导入本地参考图」。要摆新姿势则点「打开内置 3D 导演台」，摆人物、机位和视线后用「取当前画面作为参考」回到姿态预览。可从「导演台使用教程」查看取景和关键帧步骤。",
                "Open Character pose design from the home page. Use Import local reference if you have an approved pose image. For a new pose, select Open built-in 3D Director Desk, arrange the actor, camera and eyeline, then choose Use current frame as reference. See 3D Director Desk guide for framing and keyframes.",
            )),
            (("确认并带入项目", "Confirm and send to a project"), (
                "在「参考图预览」看姿势轮廓和可见手脚，点「使用参考图进入生图」。选择目标项目并核对角色及服装参考。待发送预览可检查姿态图是否已带入，确认提交才使用图像接口额度。",
                "Check the pose silhouette and visible hands and feet in Reference preview, then select Use reference in image generation. Choose the target project and review character and outfit references. Check that the pose image is in the payload preview. Confirming submission uses image API quota.",
            )),
            (("取景失败时", "If a frame cannot be captured"), (
                "确认导演台仍属于发起取景的项目，完成后从原任务接收。也可从本地导入静帧，再完成预览。生成好候选后，返回图像任务核对实际人物和姿势。",
                "Check that the Director Desk belongs to the task that requested the capture, then receive the frame in that task. You can also import a local still. After generation, review the candidate’s character and pose in the image job.",
            )),
        ),
    ),
    "director": GuideTopic(
        ("内置 3D 导演台", "Built-in 3D Director Desk"),
        (
            "在本机摆人物和机位，取静帧，或用关键帧安排最多五秒的动作片段。",
            "Stage actors and cameras locally, capture a still, or keyframe an action clip up to five seconds long.",
        ),
        (
            (("从发起任务进入", "Open from the source task"), (
                "在「角色动作设计」或「人物动作编排」点「打开内置 3D 导演台」。先在视口添加人物和道具，再摆姿势、调视角。取静帧时按「取当前画面作为参考」，软件会送回发起取景的任务。",
                "Choose Open built-in 3D Director Desk in Character pose design or Action sequencing. Add actors and props from the viewport, then pose them and adjust the camera. Use current frame as reference returns a still to the task that opened the desk.",
            )),
            (("记录关键帧", "Record keyframes"), (
                "展开「动作片段」，设定时长。在起点选择人物调整位置、朝向和姿势，点「添加关键帧」。移到下一时刻调整并再加一帧。需要交接道具时可在「道具轨」记录归属。拖动时间轴或点「播放片段」检查过渡，改动后用「更新关键帧」。",
                "In Action clip, set the duration. Choose a character at the start, adjust position, direction and pose, then select Add keyframe. Move to another time and add the next key. Use the Props track to set a prop holder if needed. Scrub or choose Play clip to review transitions, and use Update keyframe after edits.",
            )),
            (("保存或带回编排", "Save or return to sequencing"), (
                "用「保存工程」把五秒动作片段存为导演台 JSON，日后用「打开工程」继续编辑。要给动作卡带入路线，可另给可见人物或道具记录至少两个路线点，再点「把轨迹带入动作编排」。单帧参考从「角色动作设计」取景。",
                "Use Save project to keep the five-second action clip in Director Desk JSON and Open project to edit it later. To make draft action cards, record at least two motion-path points for a visible actor or prop, then choose Send tracks to action sequence. For a still reference, open the desk from Character pose design.",
            )),
            (("打开或摆姿失败时", "If the desk or pose editor fails"), (
                "如果提示另一个组正在使用导演台，先回该组完成取景或关闭它。无法打开时查看安装包中的 Windows 试用说明，确认导演台组件与 WebView2 运行环境。自带模型需要兼容的人形骨架，才可编辑关节姿势。",
                "If another group is using the Director Desk, finish or close that session first. If the desk cannot open, check the Windows trial notes for the bundled editor and WebView2 runtime. Imported models need a compatible human rig for joint pose editing.",
            )),
        ),
    ),
    "layout": GuideTopic(
        ("排版与跨组交接", "Layout and group handoff"),
        (
            "对照每镜绑定板格和净板，并核对上一组末镜与下一组首镜。",
            "Map panels and clean plates to shots, then compare continuity across the group boundary.",
        ),
        (
            (("准备排版输入", "Prepare layout inputs"), (
                "从首页打开「排版与交接」。先在「批准图像」登记故事板和净板 PNG，再在排版里按镜号选图。用「绑定整图」或「在原图框选」确定区域，可用「为选中镜头画箭头」标记必要的动作或位移。",
                "Open Layout & handoff from the home page. Register storyboard and clean-plate PNGs under Approved images, then select the images by shot. Use Bind whole image or Select crop to define each area, and Mark shot motion to indicate relevant movement.",
            )),
            (("预览并确认排版", "Preview and apply layout"), (
                "点「生成排版预览」，检查 16:9 画面、格号、净板局部标签、边缘裁切、图数和正反打。中文规则下按实际素材使用九图优化选项，记录批准的合并处理。复核完成再点「确认排版并更新正式图」。有镜头或选区变动时重新预览。",
                "Select Preview layout to check 16:9 framing, panel order, clean-plate crop labels, clipping, image count and reverse angles. Under Chinese production rules, use the nine-image options where appropriate and record approved grouping. Select Apply layout after review. Preview again if shots or crop selections change.",
            )),
            (("对照跨组动作和状态", "Review continuity across groups"), (
                "点「载入下一组」选择对应 .cfproject，再点「对照前末后首」。看演员站位、轴线、动作结果、持物和设备状态能否承接。确认后可「确认本处交接」。两组各自确认正式画面后，可按需要「导出相邻组 ZIP」。",
                "Use Load next group for the matching .cfproject, then Compare boundary shots. Check blocking, action axis, outcomes, held objects and equipment state across the cut. Use Approve handoff after reviewing. Once each group’s visuals are approved, Export adjacent groups ZIP is available.",
            )),
        ),
    ),
    "deliver": GuideTopic(
        ("故事板组打包交付", "Package storyboard group"),
        (
            "先把实际画面和两份交付文本逐镜核齐，再导出并打开 ZIP 检查内容。",
            "Review the actual visuals and both delivery text files shot by shot, then export and reopen the ZIP.",
        ),
        (
            (("从项目进入交付", "Open delivery from a project"), (
                "从首页点「故事板组打包交付」，选择准备好的项目。英文组先做「对白与图数预检」。中文组可从「对白与九图预算」复核对白和图数，再回交付页。按当前规则检查图片上限、批准对白和源镜。排版有改动时，回「排版与交接」应用并保存。",
                "Select Package storyboard group and choose the prepared project. For an English group, start with Check dialogue & image count. For a Chinese group, use Dialogue & image budget before returning to delivery. Check image limits, approved dialogue and source shots. Apply and save any changes in Layout & handoff.",
            )),
            (("逐格复核并批准", "Review and approve the visuals"), (
                "英文组用「生成逐格复核预览」，中文组用「正式交付预览」，也可单独「预览两份 TXT」。对照板格顺序、清晰度、身份、可见人数、净板局部和实际对白。发现问题回对应工序修复，重新预览后才点「确认本版画面」。",
                "For an English group, use Preview panels. For a Chinese group, use Preview final delivery or Preview both TXT files to inspect the texts alone. Check panel order, clarity, identity, visible cast, clean-plate crops and dialogue. Fix problems in the relevant stage, then preview again before choosing Approve current visuals.",
            )),
            (("验证和查看 ZIP", "Validate and reopen the ZIP"), (
                "英文交付可用软件内置的严格校验。中文正式 ZIP 需要匹配的中文版校验脚本，先在主窗口选择，再点「验收并导出 ZIP」。在可写目录保存后，打开最终 ZIP 查看实际图像、TXT 和说明，用「检查验收」也可重新检查。交付预检与打包本身无需模型接口。",
                "English delivery can use the bundled strict validator. For final Chinese delivery, select the matching Chinese production validator in the main window, then use Validate & export ZIP. Save in a writable folder and reopen the final ZIP to inspect its images, texts and notes. Inspection & validation can also check the exported archive. Local preflight and packaging require no model API.",
            )),
            (("验收未通过时", "If validation fails"), (
                "从报告定位到对应镜头、图片或文本，修正实际内容后再次预览、确认并导出。项目画面更新后重新执行交付复核，确保交接使用的是有效 ZIP。",
                "Use the report to locate the affected shot, image or text. Fix the underlying content, preview and approve again, then export. Repeat delivery review after visual updates so the handoff uses the valid ZIP.",
            )),
        ),
    ),
}
