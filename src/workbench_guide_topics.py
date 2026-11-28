"""Bilingual walkthroughs for the rest of the workbench."""

from .storyboard_guide_topics import GuideTopic


WORKBENCH_TOPICS = {
    "general": GuideTopic(
        ("工作台与项目文件", "Workbench and files"),
        (
            "从手里的文件选入口。一级页面固定在顶部，单组制片和批量任务在各自的标签中编辑。",
            "Choose a starting point based on the files you have. Top-level pages stay at the top, and group and batch tasks have their own tabs.",
        ),
        (
            (("剧本、项目和交付包", "Scripts, projects and delivery archives"), (
                "只有 TXT 或 Markdown 时，从「故事板制作」进入「剧本创作」。已有 .cfproject 时点「继续已有项目」，迁移时带上同名 .assets 文件夹。多集定稿走「批量制作中心」，已有交付 ZIP 走「检查验收」。电商参考视频走「电商信息流视频复刻」，项目保存为 .cfecom。",
                "Start in Storyboard production → Script writing with a TXT or Markdown script. Use Resume saved project for a .cfproject and keep its companion .assets folder when moving it. Use Batch production center for episode scripts, Inspection & validation for a delivery ZIP, or E-commerce video recreation for a reference clip and .cfecom project.",
            )),
            (("切换语言和任务", "Switch language and tasks"), (
                "「中文 / English」仅切换界面，新建前另选制作规则。已有项目沿用其规则。窗口窄时，从已打开任务的下拉菜单找回标签，先核对项目和集次。关闭任务时按提示决定保存或放弃草稿。顶部版本号可打开更新日志。",
                "Use 中文 / English to change the interface. Choose production rules separately for new projects. Existing projects keep their saved rules. On narrow windows, use the open-task menu and check the project and episode. Follow any save or discard prompt on close. Select the version at the top for the changelog.",
            )),
            (("直接打开离线练习", "Open an offline exercise"), (
                "在本页点「打开电商练习」「打开多集练习」或「打开验收练习」，选择文件夹。程序在单独目录准备可编辑的素材和项目。电商已带入合成短视频及产品照，多集可查 EP02 / SB02，验收可检查两组合成 ZIP 并回单组返修。",
                "On this page, choose Open e-commerce practice, Open multiple-episode practice or Open delivery review practice and select a folder. The app puts the editable files in a separate directory. E-commerce opens with a synthetic clip and product photo, batch contains EP02 / SB02, and review starts from a synthetic two-group ZIP with source projects for repairs.",
            )),
        ),
    ),
    "guide_navigation": GuideTopic(
        ("查找与返回教程", "Find and leave help"),
        (
            "遇到操作问题，可从目录查找或从当前工具进入对应章节。中英文教程均可离线打开。",
            "Use the contents or open the relevant chapter from a tool. Both language editions are available offline.",
        ),
        (
            (("在目录找章节", "Find a chapter in the contents"), (
                "打开「使用教程」。通过「故事板制作教程」找单组流程，通过「工作台操作教程」查电商、批量、验收与 API。截图和步骤显示在选中章节右侧。小窗口可滚动目录和正文。",
                "Open Tutorial. Use Storyboard production guide for group production and Workbench operations guide for e-commerce, batch, review and API connections. The screenshot and steps appear beside the selected chapter. Scroll the contents and article as needed on small windows.",
            )),
            (("看清截图上的控件", "Read the controls in a screenshot"), (
                "点「放大截图」，横向滚动看按钮和输入框，再点「适应宽度」回到整图。用顶部「中文 / English」切换当前章节的说明和截图。",
                "Select View screenshot at full size and scroll horizontally to read the controls. Select Fit to width to see the full screenshot. Use 中文 / English to switch both the current chapter’s text and screenshot.",
            )),
            (("继续发起时的任务", "Resume the originating task"), (
                "在工具页点「本页帮助」跳到对应章节。看完点「返回发起页」，可继续原来的草稿、选中项或预览。直接从目录进入时，用「教程总览」回入口，或选顶部一级页面。",
                "Use Help for this page to jump to the relevant chapter. Return to originating page resumes your draft, selection or preview. If you came from the contents, use Tutorial overview or select one of the top-level pages.",
            )),
        ),
    ),
    "ecommerce_import": GuideTopic(
        ("电商参考视频和产品", "E-commerce source and product"),
        (
            "从「电商信息流视频复刻 → 导入与产品」开始。先确认本地参考视频和自有产品资料。",
            "Start in E-commerce video recreation → Source & product, then check your local source clip and product materials.",
        ),
        (
            (("导入与保存", "Import and save"), (
                "点「新建电商项目」「导入参考视频」，选本地可解码的 MP4、MOV 等视频，最长 10 分钟。用「播放参考视频」或点封面核对画面。「保存电商项目」会保存 .cfecom。保留项目引用的视频和照片原文件。",
                "Use New project and Import reference video and choose a decodable clip up to ten minutes long, such as MP4 or MOV. Use Play reference video or the cover to inspect it. Save project writes a .cfecom. Keep the linked originals accessible.",
            )),
            (("填写产品资料", "Enter product information"), (
                "有主推产品时勾选「参考片有主推产品」，填写自有产品名并「导入产品照片」。对照原片核对实际需要的角度、包装和手持状态，再勾选「确认产品照片覆盖所需角度」。只有已批准在对白中改产品名时才填原产品名。",
                "If the reference features a product, keep that option checked, enter Your product name and use Import product photos. Check the necessary angles, packaging and use states against the clip before confirming coverage. Enter the source product name only for an approved dialogue replacement.",
            )),
            (("进入分镜并解决缺项", "Open shot analysis and resolve missing inputs"), (
                "电商练习已带入 Reference.mp4 和 Product.png。确认产品角度后点「下一步：分镜分析」。可用「检测镜头切点」读取这段三秒合成片。若提示资料缺失，核对视频路径、自有产品名、导入照片和确认项。更换参考视频会在确认后清除旧分镜和制作资产绑定。",
                "The e-commerce exercise includes Reference.mp4 and Product.png. Confirm photo coverage and select Next: Shot analysis. Run Detect candidate cuts on the three-second synthetic clip. If inputs are missing, check the video path, product name, imported photos and coverage confirmation. Replacing the source clears prior shots and production asset links after confirmation.",
            )),
        ),
    ),
    "ecommerce_shots": GuideTopic(
        ("电商分镜与原声对白", "E-commerce shots and dialogue"),
        (
            "按参考视频的实际时间、场景和原语言对白整理分镜，再核对分组和产品入镜。",
            "Record actual timing, scenes and original-language dialogue, then check the grouping and product appearances.",
        ),
        (
            (("整理镜头", "Build the shot list"), (
                "「检测镜头切点」在本地列候选，也可「添加镜头」或「导入分镜 JSON」。双击镜头编辑，用「查看参考帧」核对时间、场景、轴线和动作。「导入原声对白 TXT」可留存原文，再把对应原语言台词和说话人录入每镜。「导出分镜 JSON」可保存分镜交换文件。",
                "Use Detect candidate cuts locally, Add shot, or Import shot JSON. Double-click a shot to edit it. Use View reference frame to check timing, scene, axis and action. Import original dialogue TXT to keep the transcript, then record original-language lines and speakers on the matching shots. Export shot JSON saves the shot list as an exchange file.",
            )),
            (("可选 AI 看图建议", "Optional vision model suggestions"), (
                "已有实际时间码时可点「AI 辅助看图拆镜」，从所选镜头起最多取 12 镜。确认发送后，视觉模型会收到抽样画面、分镜信息和已填的产品名，可能消耗服务商额度。收到的描述需对照原片复核，并核对原声对白。",
                "Draft shots from frames with AI uses up to 12 timed shots starting from the selection. After confirmation, the vision model receives sample frames, shot details and any entered product name. This can consume provider quota. Verify the suggested descriptions and original dialogue against the clip.",
            )),
            (("确认分组", "Approve grouping"), (
                "检查时间重叠和超过 15 秒的单镜，按实际切点修正。实际出现产品的镜头需单独标记，普通道具里移除产品名称。「公共连续性」可记录共用摆位和状态。点「确认分镜并分析资产」按场景、时长和格数分组。分组改变后重新确认并核对资产绑定。",
                "Correct overlapping intervals or shots longer than 15 seconds at actual cuts. Mark shots where the product appears and remove its name from ordinary props. Use Shared continuity for recurring staging and states. Approve shots & audit assets groups by scene, duration and panel limits. Reapprove and check asset links after grouping changes.",
            )),
            (("离线练习：核对样例镜头", "Offline practice: compare the sample shots"), (
                "先点「检测镜头切点」查看三秒样例片的候选，再用「导入分镜 JSON」选择练习目录的 Shots.json，对照原视频核对 01、02、03 三镜的时间码、动作和产品标记。点「确认分镜并分析资产」，样例进入 SB01。",
                "First run Detect candidate cuts on the three-second sample, then use Import shot JSON to select Shots.json from the practice folder. Compare the timecodes, actions and product markings in shots 01, 02 and 03 against the clip. Choose Approve shots & audit assets to prepare sample group SB01.",
            )),
        ),
    ),
    "ecommerce_assets": GuideTopic(
        ("电商资产与彩色故事板", "E-commerce assets and boards"),
        (
            "先准备角色、场景、道具和自有产品，再制作各组彩色故事板。",
            "Prepare characters, scenes, props and your own product before completing each group’s color storyboard.",
        ),
        (
            (("核对资产清单", "Check the asset audit"), (
                "确认当前分镜后点「刷新资产清单」。逐项选择角色、场景或道具，点「导入批准图像」并预览确认。普通资产使用 16:9。角色图核对同一新面貌在正、侧、背全身和正脸特写中的一致性。产品行用「合成自有产品总图」从已确认照片本地合成。",
                "Approve current shots, then use Refresh asset audit. Select each character, location or prop, use Import approved image and confirm the preview. Use 16:9 for these assets. Check the redesigned face across front, side, back and close-up. Compose product sheet builds the product art locally from confirmed photos.",
            )),
            (("制作组故事板", "Prepare the group board"), (
                "每组用一张至少 1080×1920 的 9:16 彩色合板。选对应组的故事板行，导入并核对实际格数、镜号、顺序、产品和人物连续性。尺寸不合规则换合格图。素材库用于浏览，交付取各资产行绑定的批准图。",
                "Each group uses one color 9:16 board at 1080×1920 or larger. Select its board row and import the image. Check panel count, IDs, order, product details and continuity. Replace images that fail the size check. The media library is for browsing. Delivery uses the approved image bound to each asset row.",
            )),
            (("API 候选与查询", "Image API candidates and queries"), (
                "选择资产行，点「用 API 制作选中资产」，核对预览中的模型、提示词和参考图顺序。确认后才发送并可能计费。已有异步提交用「查询生图任务」，图像返回后核对再采纳。若分镜未确认，先回分镜分析确认本版。",
                "Select an asset and use Generate selected asset with API. Review the model, prompt and reference order before confirming the request, which can consume quota. Use Check image job for an existing submission and inspect the returned candidate. If current shots are unapproved, return to Shot analysis and approve them first.",
            )),
            (("离线练习：绑定两张图", "Offline practice: bind two images"), (
                "在样例资产清单选「产品展示台」场景行，用「导入批准图像」导入 Scene.png 并确认。点「合成自有产品总图」，核对后确认。再选 SB01 故事板行，导入 SB01-Board.png，核对顺序与实际画面后确认。点「下一步：提示词与交付」。",
                "Select the 产品展示台 scene row and use Import approved image to bind Scene.png after reviewing it. Confirm the result of Compose product sheet. Then select the SB01 board row and import SB01-Board.png. Check the panel order and visuals before confirming. Choose Next: Prompts & delivery.",
            )),
        ),
    ),
    "ecommerce_delivery": GuideTopic(
        ("电商提示词与交付", "E-commerce prompts and delivery"),
        (
            "预览 Seedance 2.0 提示词和交付成员，逐项复核后验收导出。",
            "Preview the Seedance 2.0 prompts and delivery members, then verify them before exporting.",
        ),
        (
            (("准备并检查预览", "Prepare and inspect the preview"), (
                "在「提示词与交付」点「预览 SD2 提示词」，核对每组镜头顺序和原语言对白。点「生成交付预览」，选中清单中的图像或 TXT 后点「查看选中文件」。核对格号、产品细节、独立人物资产和清晰度。预览在本机运行。",
                "In Prompts & delivery, use Preview SD2 prompts to check shot order and original dialogue in each group. Select Prepare delivery preview, then choose an image or TXT and use Review selected file. Check panel IDs, product details, individual character sheets and clarity. Previewing runs locally.",
            )),
            (("导出及重新检查", "Export and check again"), (
                "逐格核对后勾选画面、原语言对白、产品细节及独立人物资产的确认项，再点「验收并导出 ZIP」。选择新文件名，完成界面会显示路径及 SHA-256。重开 ZIP 抽查成员、故事板和提示词。有音轨的原片须逐镜填写对白，明确无对白填「无」，听不清填「[听辨不清]」。缺图时回资产页绑定正式图，图像或分镜变更后重新生成预览。",
                "After reviewing the panels, confirm the checkbox for visuals, original dialogue, product details and individual character sheets, then use Validate & export ZIP. Choose a new file name. The result shows the path and SHA-256. Reopen the ZIP and inspect members, boards and prompts. For clips with audio, record dialogue for each shot. Enter 无 for no dialogue or [听辨不清] for unintelligible speech. Bind missing approved images, and prepare a fresh preview when images or shots change.",
            )),
            (("离线练习：导出并重开", "Offline practice: export and reopen"), (
                "用已确认的样例场景、产品总图和 SB01 故事板生成交付预览。逐项查看板图与 TXT 后勾选复核项，导出到练习目录，再打开 ZIP 核对 SB01 成员和提示词。整条练习可在本机完成。",
                "Prepare the delivery preview using the approved sample scene, product sheet and SB01 board. Review the artwork and TXT files, check the review box and export to the practice folder. Reopen the ZIP and inspect the SB01 files and prompts. The entire exercise runs locally.",
            )),
        ),
    ),
    "batch_import": GuideTopic(
        ("批量导入一集或多集", "Import episodes into a batch"),
        (
            "从「故事板制作 → 批量制作中心」管理一集或多集定稿，每集都有独立的原稿和分镜。",
            "Use Storyboard production → Batch production center to manage one or more scripts. Each episode has its own source and shots.",
        ),
        (
            (("新建或继续批次", "Create or open a batch"), (
                "新建前先选制作规则，点「新建批次」保存 .cfbatch。要继续原批次，点「打开批次」。移动或备份时保留同名 .batch 文件夹。找不到批量项目数据时，先核对两个名称及所在目录。",
                "Choose production rules before using New batch to save a .cfbatch. Use Open batch to resume. Move or back up the .cfbatch with its companion .batch folder. If the batch data is unreadable, check their names and location.",
            )),
            (("每个文件一集", "One script file per episode"), (
                "点「导入剧本」，选择一份或多份 UTF-8 TXT／MD，每个文件对应一集。核对「当前集」列表，再点「继续到整集规划」。修改原稿时，选正确集次后点「更新本集原稿」，然后复查受影响的旧组和新规划。",
                "Use Import scripts and select one UTF-8 TXT or MD per episode. Check the Episode list and choose Continue to episode plan. To revise a script, select its episode, use Revise script, then check the affected old groups and new plan.",
            )),
        ),
    ),
    "batch_plan": GuideTopic(
        ("整集规划与定位镜头", "Episode plan and shot lookup"),
        (
            "用原文、组号和镜号定位各集分镜，核对各组的内容覆盖和对白。",
            "Find shots by source text, group or shot ID, then check each group’s script coverage and dialogue.",
        ),
        (
            (("从原稿定位到单组", "Find a group from the script"), (
                "选「当前集」，进入「整集规划」。在「查找原文或镜号」输入词句或镜号，核对结果的原稿行、说话人和组／镜。双击记录或点「打开单组制片」，也可选「目标组」再点「打开目标组」。用多集练习选 EP02 / SB02，再从组内点「回到批量制作」，核对集次和组号。",
                "Select Episode and open Plan. Enter a phrase or shot ID in Find passage or shot. Check the line, speaker and group / shot. Double-click a row or use Open group editor. You can also choose Group and use Open target group. In the practice batch, open EP02 / SB02 and use Return to batch production to verify the same episode and group.",
            )),
            (("细拆与重新分组", "Split and regroup"), (
                "选动作段后点「细拆动作段」，只在可见动作变化处增删换行，保留全部原文并去掉空行。调整组界时用「从此镜另起一组」或「与前一组合并」。选到对白、组首或第一组时，换到该操作适用的行。",
                "Choose an action passage and use Split action passage. Change line breaks at visible beats, preserve every character and remove blank lines. Use Start group here or Merge with previous to adjust a boundary. Select a suitable row if you clicked a dialogue row, a group start or the first group.",
            )),
            (("确认后再进队列", "Approve before queuing"), (
                "用「查看整集原文」核对覆盖、组界和对白保全，再点「确认本集规划」。多集批次逐集核对。更新原稿或重新分组后，先按新规划确认再加入队列。",
                "Use Read script to check coverage, group boundaries and unchanged dialogue, then choose Approve episode plan. Check each episode in a multi-episode batch. After a revision or regroup, approve the new plan before queuing it.",
            )),
        ),
    ),
    "batch_assets": GuideTopic(
        ("批次公共资产和依赖", "Batch assets and requirements"),
        (
            "公共资产按身份、状态和批准版本登记，各组据此查找、复用或补图。",
            "Register shared assets by identity, state and approved version so groups can find exact matches, reuse them or fill gaps.",
        ),
        (
            (("批准和预览", "Approve and preview assets"), (
                "点「批准本地资产」选择已核对 PNG 原图，填写身份／资产名、状态／造型、批准版本和画面核对记录。用「打开素材库」浏览或放大核对。制作用登记的批准资产。",
                "Use Approve local asset to select a verified PNG original. Fill Identity / asset, State / look, Version and Review notes. Use Open media library to browse or enlarge images. Production uses the approved record.",
            )),
            (("为选中组复用和补缺", "Reuse or fill gaps for a group"), (
                "核对当前集和目标组，再选批准资产并点「复用到所选组」。「指定依赖」用于锁定状态、版本和参考／交付用途，点「绑定已批准依赖」后核对剩余缺项。多集练习的 EP02 / SB02 可绑定预置的关门场景参考。",
                "Check Episode and Group, select the approved asset, and use Reuse in selected group. Use Require asset to lock its state, version and reference or delivery use. Use Bind approved matches and check remaining gaps. The sample EP02 / SB02 has a matching closed-door scene reference to bind.",
            )),
            (("安排图像候选", "Queue an image candidate"), (
                "缺少合格图像时，点「安排资产生图」填写类型、身份、状态和画面要求。此处只建任务。运行队列并满足前置条件后，才可能发送请求和计费。采纳前重新核对实际画面及所属组。",
                "Use Queue asset image for missing art and enter the type, identity, state and brief. This creates a local job. Running the queue with dependencies met may submit a billable request. Check the returned art and its group before approval.",
            )),
        ),
    ),
    "batch_queue": GuideTopic(
        ("批量队列与候选", "Batch queue and candidates"),
        (
            "按集或按组查看任务进度和候选，使用原任务记录继续处理。",
            "Review progress and candidates by episode or group and continue from the existing job records.",
        ),
        (
            (("选任务并设上限", "Choose tasks and set a limit"), (
                "在「执行队列」勾选分镜、提示词、故事板或净板，点「本集加入队列」或「多集加入队列」。选文本／生图模型和「本批 API 请求上限」，再点「运行／继续」。上限统计累计新提交，费用由服务商计。设为 0 会阻止新提交，已有的异步任务仍可能联网查询。",
                "In Job queue, select Shot, Prompt, Board or Clean plate, then choose Queue episode or Queue all episodes. Select the text and image models and set Batch request limit before Run / resume. The limit counts cumulative new submissions. Provider billing applies. Zero blocks new submissions, while existing asynchronous jobs may still be queried.",
            )),
            (("核对并采纳候选", "Review and approve candidates"), (
                "看清集次、组号和镜号，通过「查看／采纳候选」回到原单组图像任务或查看文字。同类文字也可「整组审核文字」。核对原稿、镜号和图片后再采纳。可用「本次请求后暂停」。任务可能发送本镜原稿、交接状态、提示词或已批准参考图，内容随任务类型变化。",
                "Check the episode, group and shot. Review candidate returns to the original group image task or displays text. Use Review group text for candidates of the same type. Check sources, shot IDs and art before approving. Use Pause after request as needed. Submitted content can include source text, handoff state, prompts or approved references, depending on the task.",
            )),
            (("等待前置步骤或核实扣费", "Blocked jobs or unconfirmed submissions"), (
                "待前置步骤时先看详情，补齐规划批准、资产依赖或上一步结果。需核实扣费时，到服务商查原任务号或记录，再决定是否「重试选中任务」。查询异步任务时使用原服务商、基础地址和模型。",
                "For a blocked job, read the details and resolve the missing plan approval, asset requirement or preceding result. If submission is uncertain, check the original job ID or provider record before Retry selected. Query with the original provider, base URL and model.",
            )),
        ),
    ),
    "batch_delivery": GuideTopic(
        ("验收并导出整集和多集", "Deliver episodes and series"),
        (
            "在「验收交付」检查原稿覆盖、每组画面和相邻组交接，再按集或整批导出。",
            "In Review & delivery, check script coverage, group visuals and adjacent handoffs before exporting an episode or series.",
        ),
        (
            (("复查覆盖和实际画面", "Check coverage and visuals"), (
                "选「当前集」，点「复查本集覆盖」「查看原稿覆盖」，从镜号确认原文覆盖。选待复核的组，点「打开本组复核」看实际板格、净板及文字。组间衔接待核对时点「打开组间衔接」，核对前组末格与当前组首格。",
                "Select Episode and use Recheck coverage and Script coverage to match the source to shot IDs. Select a group awaiting review and use Open group for review to check its panels, clean plates and text. Use Open group handoff to check the outgoing and incoming shots at a pending boundary.",
            )),
            (("导出整集或多集", "Export an episode or a series"), (
                "确认各组后点「导出整集 ZIP」，按提示选择该规则的校验脚本和保存位置。整集包包含组包、交付目录和原稿覆盖索引。「导出多集总包」汇集各集包。覆盖或复核未完成时，从组列表定位修复，回本页刷新后重试。",
                "After review, choose Export episode ZIP. Follow any prompt to select a validator for the production rules and choose a destination. The episode archive contains group ZIPs, a delivery list and a source coverage index. Export series ZIP collects episode archives. If checks are pending, find and repair the group, refresh the episode and retry.",
            )),
        ),
    ),
    "review_zip": GuideTopic(
        ("检查交付 ZIP", "Validate a delivery ZIP"),
        (
            "从「检查验收」校验 ZIP，再按问题、组号、镜号或成员文件打开细查。",
            "Use Inspection & validation to check a ZIP, then inspect its issues, groups, shots or member files.",
        ),
        (
            (("选择包和校验规则", "Select the archive and rules"), (
                "在「交付 ZIP」点「浏览」，直接选择未解压 ZIP。选与交付包相符的制作规则。中英文制作规则分别使用对应的内置严格校验器，也可为当前语言指定可信的校验脚本。点「开始验收」，在「验收结果」「完整报告」查看问题与范围。",
                "Use Browse beside Delivery ZIP and select the unopened archive. Select the rules used to produce it. Each language has its own bundled strict validator. You can also select a trusted validator for the current language. Click Validate ZIP, then inspect Validation results and Full report.",
            )),
            (("区分文件和内容检查", "Read the scope of validation"), (
                "看到「文件完整性检查通过 · 工作流未验」时，表示尚未跑规则校验。选择对应校验器后重新验收。复用原图路径不可访问时，可用资产登记库恢复来源，或明确标为未验证。自动验收通过后仍用「逐格复核」看画面和文字对应。",
                "File integrity passed · Workflow unverified means workflow validation has yet to run. Select the appropriate validator and recheck. Restore inaccessible reusable originals through the asset registry or explicitly mark them unverified. After automated checks, use Review panels to compare the images and text.",
            )),
            (("试一次本地验收", "Try a local validation"), (
                "从总览章节点「打开验收练习」。程序会填好合成示例 ZIP 路径，准备独立的两组项目和 Practice-Assets.sqlite3 资产登记库。确认选「英文影片制作」及内置校验器，再点「开始验收」。可选 SB01 的包内图像练习从验收返回制片。",
                "Choose Open delivery review practice on the workbench and files chapter. The app fills the synthetic ZIP path and prepares separate group projects and the Practice-Assets.sqlite3 asset registry. Confirm English film production and the bundled validator, then click Validate ZIP. Choose an SB01 image to practice returning to production.",
            )),
        ),
    ),
    "review_images": GuideTopic(
        ("图片比例和可选审图", "Image checks and AI review"),
        (
            "可在本机查图片尺寸，也可在确认后把一张选中的包内图片发给视觉模型。",
            "Check image dimensions locally, or explicitly confirm sending one selected archive image to a vision model.",
        ),
        (
            (("检查本地文件", "Inspect a local file"), (
                "从「检查验收」点「图片大小与比例」，再「选择本地图片」。上方显示实际格式、像素尺寸、宽高比和文件字节。可打开 PNG、JPEG 和 WebP。比例提示以横向 16:9 为标准。电商 9:16 合板按电商规则核对。",
                "In Inspection & validation, open Image dimensions & ratio, then Choose local image. Read the actual format, pixel size, aspect ratio and file size. PNG, JPEG and WebP are accepted. The ratio comparison uses landscape 16:9. Check vertical 9:16 e-commerce boards against their own workflow rules.",
            )),
            (("提交一张选中的包内图", "Send one selected archive image"), (
                "验收 ZIP 后选一张可预览的图，再点「AI 辅助看图」。检查视觉模型和可选的审图重点。点「发送图片并分析」并确认接收地址后，才会发送所选图片或其压缩副本、审图规则和补充重点，可能消耗服务商额度。返回结果需人工核对。",
                "After validating a ZIP, select a previewable image and choose AI image review. Check the vision model and optional review focus. Send image for review asks you to confirm the destination before sending the selected image or its compressed copy, review instructions and focus. This can use provider quota. Review the returned findings manually.",
            )),
            (("图片无法读取或按钮置灰", "Image unreadable or review unavailable"), (
                "「图片检查未完成」时，换一份可完整解码的原图。ZIP 审图按钮置灰时，先选一个可预览的图片成员。若提示配置未完成，到「API 接入 → AI 审图」核对模型 ID、密钥及图片输入权限。",
                "If image inspection is incomplete, choose a readable original. Select a previewable image member if AI image review is disabled. If setup is incomplete, check model ID, credentials and image-input access in API connections → AI image review.",
            )),
        ),
    ),
    "review_cuts": GuideTopic(
        ("景别机位与格间衔接", "Framing and cut continuity"),
        (
            "验收 ZIP 后逐格核对故事板和净板，或并排比较前镜和后镜。",
            "After ZIP validation, inspect the storyboard and clean plate for each shot, or compare outgoing and incoming shots side by side.",
        ),
        (
            (("逐格放大看实际画面", "Inspect actual panels"), (
                "在验收结果选中一镜或同组文件，点「逐格复核」。按镜号对照板格、净板对应局部、制片 TXT 和 SD2 提示词。可拖框放大并返回整图。提示没有唯一净板对应时，回源项目和局部表核对镜号与选区。",
                "Select a shot or group member and use Review panels. Compare the board, clean-plate crop, production TXT and SD2 prompt by shot ID. Drag to enlarge a region or return to the full image. If the clean-plate mapping is ambiguous, check the source project, shot ID and crop table.",
            )),
            (("逐一检查切点", "Inspect cuts"), (
                "点「景别机位与格间衔接」，用「上一处」「下一处」对看前、后镜。勾选「仅跨页或跨组」可集中查边界。核对景别、机位、视线、角色数量、动作和物件的前后状态。跨不相邻组时需找齐对应组再判断。",
                "Use Framing & cut continuity and Previous cut or Next cut to compare shots. Choose Across pages or groups to focus on boundaries. Check framing, angle, eyelines, character counts, movement and object state. Locate the matching group if the two groups are not consecutive.",
            )),
            (("入口打不开", "When a viewer cannot open"), (
                "先选有效交付 ZIP 并运行验收。前后镜对照至少需要两条可读镜头记录。若缺图或格号错位，从「回到制作返修」打开相应工序，修复后重新导出并再复核。",
                "Validate a delivery ZIP first. Comparison requires at least two readable shot records. If a frame is missing or IDs do not match, use Open production task for repair, fix the original project and review the new export again.",
            )),
        ),
    ),
    "review_repair": GuideTopic(
        ("定位返修与重新打包", "Locate repairs and repackage"),
        (
            "从验收报告找到正确的原项目和文件。修复后生成新 ZIP，并复验实际输出。",
            "Use the review to find the correct source project and files. Produce a new ZIP after repair and validate the actual output.",
        ),
        (
            (("回到正确的生产任务", "Return to the correct production task"), (
                "验收源 ZIP 后，选能指向单组的报告项或包内图，点「回到制作返修」。核对项目名、集次、组号和规则。没有匹配时，手动选择本组 .cfproject。报告提示镜头源 ID 不符时，找到和原包对应的项目版本再试。旧包缺可验证源 ID 时，按提示手动核对。",
                "After validating the source ZIP, select an issue or member tied to one group and use Open production task for repair. Confirm project, episode, group and rules. Select the group’s .cfproject manually if needed. If source IDs do not match, locate the project revision used for the original ZIP. For old packages without traceable IDs, check the shot manually as prompted.",
            )),
            (("试用本地候选并验收新组包", "Try the local candidate and check the new group ZIP"), (
                "用练习副本定位到 SB01-01 的净板。打开该组「资产图生成」，选预置的局部合成候选，核对灯罩选区和批准参考图。点「批准并加入正式交付」，填原文件名、新版本及实际核图记录，再勾同名替换并确认。到「故事板组打包交付」重新生成逐格预览，点「确认本版画面」后导出新 ZIP。在「资产与返修 → 资产登记」选择本次导出生成的 SB01.assets.sqlite3，再打开新 ZIP 验收。",
                "In the practice copy, find the clean plate for SB01-01. Open Asset image generation for that group, then choose the included local composite. Check the lamp area against the approved reference. Use Approve for delivery with the original filename, a new version and inspection notes. Select the replacement checkbox and confirm. In Package storyboard group, refresh the panel preview, use Approve current visuals and export a new ZIP. In Assets & repairs → Asset registry, select the SB01.assets.sqlite3 created by this export before validating the new ZIP.",
            )),
            (("从返修后的目录打包", "Package a repaired delivery folder"), (
                "已有返修目录时，进「资产与返修 → 返修打包」。填写完整镜号后点「查看关联文件」，核对故事板、净板、两份 TXT 和 README。选择已修目录与新 ZIP，点「复验并打包」，用原 ZIP 的增删改清单复核并「保存报告」。搬迁原图可用「资产登记 → 按 SHA-256 找回」。",
                "With a repaired folder, open Assets & repairs → Repair packaging. Enter the full shot ID and choose Find affected files to check the board, clean plate, both TXT files and README. Select the repaired folder and a new ZIP, then use Recheck & package. Check added, changed and removed members against the original ZIP and use Save report. For moved originals, use Asset registry → Recover by SHA-256.",
            )),
        ),
    ),
    "jobs": GuideTopic(
        ("后台任务和恢复", "Jobs and recovery"),
        (
            "「任务中心」帮助找回本次运行的验收、工作台生图和 AI 审图。",
            "Job Center helps reopen delivery checks, workbench image requests and AI image reviews from this session.",
        ),
        (
            (("按来源找回", "Find a task by source"), (
                "从「故事板制作」或「检查验收」进「任务中心」。选任务行，核对来源中的项目、组号或 ZIP 成员，再点「返回原任务」。关闭原工序标签后，已提交的工作台生图或审图仍可在本次运行内找回。批量队列进度在对应批次查看。",
                "Open Job Center from Storyboard production or Inspection & validation. Select a row, confirm its project, group or archive member, then choose Open originating task. Submitted workbench image and review requests remain accessible this session even after their tabs close. Check batch queue progress in its batch.",
            )),
            (("结果已返回但保存失败", "A returned result needs saving"), (
                "状态为「结果保存待重试」时，确认目标目录可写，再点「重试保存」。这一步只重试写已有结果。若状态为「等待核对服务商」，先在原服务侧核对请求，避免重复提交和重复计费。",
                "If the result needs saving, confirm the destination is writable, then use Retry saving to write the existing result. If the status is Check provider status, verify the original request with that provider before submitting another billable request.",
            )),
        ),
    ),
    "api": GuideTopic(
        ("按用途配置 API", "Configure API connections"),
        (
            "为文本创作、AI 审图和图像生成分别设置模型。配置和密钥仅用于本次软件运行。",
            "Configure separate models for text drafting, AI image review and image generation. Settings and credentials last for the current session.",
        ),
        (
            (("选择模型能力", "Choose the model capability"), (
                "打开「API 接入」。「文本创作」用支持文本和所需 JSON 输出的模型。「AI 审图」需要支持输入图片。「图像生成」需要直接输出图片，参考图和局部编辑还要核对该服务支持的模式。混元签名接口需要配套 SecretId 和 SecretKey。",
                "Open API connections. Text drafting needs text and any required JSON output. AI image review needs image input. Image generation needs image output. Check available modes for reference images or local edits. The signed Hunyuan connection requires its paired SecretId and SecretKey.",
            )),
            (("填写并保存本次设置", "Enter settings and save"), (
                "选服务商，填写其 HTTPS 基础地址、准确模型 ID 和密钥，点「保存本次设置」。基础地址填服务商给的根地址，省略 messages 或 chat/completions。文本和审图可在同服务商、同基础地址的情况下「带入另一用途的 Key」。改基础地址后要重新填密钥。",
                "Select the provider, enter its HTTPS base URL, exact model ID and credentials, and choose Save for this session. Use the provider’s base URL without messages or chat/completions. Copy key from other purpose works between text and review for the same provider and base URL. Re-enter credentials when changing the URL.",
            )),
            (("保存后怎样核对", "Verify after saving"), (
                "保存时只检查配置格式。缺密钥时可以先保存接口和模型，正式提交前补齐。用「返回发起页」回到原工序，提交前核对接收地址、模型、提示词或所选图片。确认发送才使用服务商额度。若服务返回权限或模型报错，检查账户权限、模型 ID 和密钥再决定重试。",
                "Saving checks the configuration format locally. You can save the URL and model first and add credentials before submitting. Use Return to originating page, then check the destination, model, prompt or selected images. Confirming the request can use provider quota. For access or model errors, check permissions, model ID and credentials before retrying.",
            )),
        ),
    ),
}
