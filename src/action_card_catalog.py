"""Original, bilingual action-card starters for staging fictional scenes."""

from dataclasses import dataclass
from pathlib import Path


ACTION_PREVIEW_DIRECTORY = Path("assets/action_previews")

PRESETS = {
    ("日常与表演", "Everyday & performance"): (
        (("推门后等一拍", "Open the door and pause"),
         ("门扇打开后，人物停在门槛内侧。视线先扫过房间，再落到窗边的亮处，手仍扶着门。",
          "The character opens the door and pauses inside the threshold. Their eyes scan the room and settle on the lit window while their hand stays on the door."),
         ("门", "Door")),
        (("起身时发现异样", "Notice something while standing"),
         ("人物扶住椅沿起身，看到桌角的东西后半途停住。末帧保持身体半立和视线落点。",
          "The character starts to stand with a hand on the chair. Something on the desk stops them halfway up. Hold that posture and eye line at the cut."),
         ("椅子", "Chair")),
        (("递出后松手", "Hand over an object"),
         ("两人之间出现短暂停顿。接收者稳稳托住物件，递出者这才松手，末帧清楚交代物件归属。",
          "The exchange pauses. Once the receiver has the object, the giver lets go. End on the new owner holding it."),
         ("随身小物", "Small personal item")),
        (("停步侧耳", "Stop and listen"),
         ("脚步在墙边停下，肩膀随后静下来。人物朝声音来源偏头，保留声源在画外的空间关系。",
          "The footsteps stop by the wall, followed by the shoulders settling. The character tilts their head toward the offscreen sound."),
         ("", "")),
        (("放下杯子才开口", "Set down the glass before speaking"),
         ("杯底落到桌面后，手指慢慢收回。人物视线离开杯口，抬眼看向听者并开口。",
          "The glass touches the table and the fingers withdraw. The character lifts their eyes to the listener and begins speaking."),
         ("杯子", "Glass")),
        (("转身前犹豫", "Hesitate before turning away"),
         ("人物的脚已经朝出口转过去，视线还留在身后。停一拍，目光离开后才带动肩膀转向。",
          "The feet turn toward the exit while the eyes stay behind. After a beat the gaze breaks and the shoulders follow."),
         ("", "")),
    ),
    ("双人配合与救援", "Partner movement & rescue"): (
        (("伸手得到回应", "Reach out and get a response"),
         ("一人伸出手，另一人先看手再看脸，随后主动接住。切点放在接触成立、双方目光都能读清的时候。",
          "One character offers a hand. The other looks at it, looks up, then accepts. Cut once the contact and both eye lines are clear."),
         ("", "")),
        (("一人扶起另一人", "Help a partner to their feet"),
         ("站立的人先靠近到伸手可及的位置。两人接触后，受扶者自己抬起身体，末帧留出他们共同站稳的位置。",
          "The standing character closes the gap before making contact. The partner rises with their help. End with both settled in a visible position."),
         ("", "")),
        (("护送通过门洞", "Escort through a doorway"),
         ("走在前面的人停在门洞侧边，让队友从留出的通道先过。随后回看队友的落点，末帧两人在同一侧。",
          "The lead character stops to one side of the doorway and lets their partner through. They check where the partner stops. End with both on the same side."),
         ("门", "Door")),
        (("两人架着大箱让路", "Carry a crate around an obstacle"),
         ("两人各托住箱体一端，在转角同时放慢，等箱角通过后再向前。末帧箱体的朝向和两人的位置都能辨认。",
          "The pair support opposite ends of a crate. Both slow at the corner and resume once the crate clears it. End with its orientation and both positions readable."),
         ("道具箱", "Prop crate")),
        (("前人示意后人停下", "Signal to stop"),
         ("前方人物在路口停住并回看，后方人物看到手势后才止步。末帧保留两人之间的距离。",
          "The lead character stops at the intersection and looks back. Their partner stops after seeing the signal. Preserve the gap at the cut."),
         ("", "")),
        (("交接手电照明", "Pass a flashlight"),
         ("接收者从亮束侧边靠近，双方的手同时出现片刻。手电交接后，光束稳定落回同一地点。",
          "The receiver approaches from beside the beam. Both hands appear briefly. After the handoff, the light settles back on the same spot."),
         ("手电", "Flashlight")),
    ),
    ("路线、遮挡与转场", "Paths, occlusion & transitions"): (
        (("从柱后走入光里", "Step out from behind a column"),
         ("人物沿柱后已有路线前进，先露出轮廓，再完整走入光区。末帧点明脚下落点与柱子的相对位置。",
          "The character follows the established route behind the column. Their silhouette emerges before they step fully into the light. End on a clear floor position."),
         ("", "")),
        (("经过前景遮挡切镜", "Cut behind a foreground obstruction"),
         ("前一个画面在人物走进前景遮挡时结束。下一画面从同一次步态出遮挡，沿用衣摆运动和前进方向。",
          "End as the foreground hides the character. Resume as they emerge in the same stride, with matching clothing movement and travel direction."),
         ("", "")),
        (("踩过门槛回身看", "Cross the threshold and look back"),
         ("人物明确跨过门槛，先完成落脚再回头看。门框留在画面边缘，供下镜确认已进入新空间。",
          "The character crosses the threshold, plants a foot, then looks back. Keep the doorframe at the edge of the image to establish the new space for the next shot."),
         ("门", "Door")),
        (("借栏杆停住", "Settle beside a railing"),
         ("人物走到栏杆附近后放慢，在固定栏杆处停稳。镜头从脚步移到扶住栏杆的手，交代结束位置。",
          "The character slows near the railing and settles beside it. Move attention from their footsteps to the hand resting on the fixed railing."),
         ("栏杆", "Railing")),
        (("逆光里换成前景视角", "Change angle on a backlit silhouette"),
         ("先见人物在门口的逆光轮廓。下一机位移到室内侧，沿用门框和地面投影确认人物在原处。",
          "Start on the doorway silhouette. Move the next camera angle inside and use the same doorframe and floor shadow to establish the character's position."),
         ("", "")),
        (("避开落下的布景", "Move clear of a falling set piece"),
         ("布景晃动时，人物先抬眼察觉，再移到已建立的空处。末帧交代布景落点和人物的新位置。",
          "The character notices the shifting set piece, then moves to an established clear area. End with both the set piece's landing and the new position visible."),
         ("泡沫布景", "Foam set piece")),
    ),
    ("刀道具", "Stage sabers"): (
        (("灯光扫过道具刀", "Light crosses a stage saber"),
         ("人物在暗处停稳。灯光沿刀道具轮廓掠过，随后重点回到人物的眼神。末帧保留道具和人物同框。",
          "The character comes to rest in shadow. Light travels across the saber silhouette before attention returns to their eyes. Finish with both in frame."),
         ("道具刀", "Stage saber")),
        (("刀停在桌沿", "Rest the saber on a table"),
         ("人物把刀道具放到桌沿的指定位置，随后松开手看向对面。下一格继承刀与桌面标记的相对位置。",
          "Place the saber on its mark at the table edge. The character lets go and looks across. Keep the prop aligned to the same mark in the next panel."),
         ("道具刀", "Stage saber")),
        (("刀影进入墙上", "Reveal the saber in shadow"),
         ("先看到墙上出现人物和道具的剪影，再切到同侧看清人物已停住。固定灯位让两个轮廓能对应。",
          "Show the character and prop first as shadows on the wall. Cut to a matching side view once the figure has stopped. Keep the light source fixed."),
         ("道具刀", "Stage saber")),
        (("刀道具让位给表情", "Move attention from saber to expression"),
         ("前景是人物手中的道具，画内另一人开口后，焦点转到持刀者脸上。末帧里原持物手仍可见。",
          "Start with the prop in the foreground. When the other character speaks, shift focus to the saber holder's face. Keep the same holding hand visible at the cut."),
         ("道具刀", "Stage saber")),
        (("放下后退到光外", "Leave the saber and step out of light"),
         ("人物把道具留在固定台面，再从台边退出光区。切镜时道具清楚留在亮处，退出方向可追踪。",
          "The character leaves the prop on the fixed platform and moves out of its pool of light. Keep the prop illuminated and the exit direction clear."),
         ("道具刀", "Stage saber")),
        (("刀光划过前景转场", "Transition behind a saber-shaped light trail"),
         ("人物转身，幻想刀光从前景掠过并铺满画面。下一格借同色光接到新的构图，保留转身方向和末帧的持物位置。",
          "As the character turns, a fantasy light trail fills the foreground. Match its color into the next composition and preserve the turn direction and final prop position."),
         ("道具刀", "Stage saber")),
    ),
    ("长枪道具", "Stage spears"): (
        (("枪杆先露出转角", "Reveal the spear at a corner"),
         ("转角处先出现长柄道具的轮廓，人物沿同一路线走出。用宽一点的画幅同时交代两端和转角位置。",
          "The long prop appears around the corner just before the character follows the same route. Frame wide enough to show both ends and the corner."),
         ("道具长枪", "Stage spear")),
        (("长枪靠到固定墙边", "Set the spear against a wall"),
         ("人物在墙侧停下，将长柄道具放到固定落点。手离开后道具保持原位，给下一镜保留交接锚点。",
          "The character stops beside the wall and rests the long prop on its mark. It stays in place after release, establishing continuity for the following shot."),
         ("道具长枪", "Stage spear")),
        (("长枪过窄门", "Carry the spear through a narrow door"),
         ("人物在门前停半拍，将道具沿门洞空间调整后通过。末帧既看得到后端离开门框，也看得到人物落脚。",
          "The character pauses at the door and shifts the prop to fit the opening. End once both the trailing end and the character have cleared the doorway."),
         ("道具长枪", "Stage spear")),
        (("枪尾留下固定触点", "Use the spear as a visual anchor"),
         ("末端在布景上一个能看清的点落稳，人物眼神移到远处的亮点。下一镜用同一落点确认位置连续。",
          "The end settles on a visible mark as the character looks toward a distant light. Use the same point as an anchor in the next shot."),
         ("道具长枪", "Stage spear")),
        (("并行走位保留间距", "Walk with a partner at a readable distance"),
         ("人物带着长柄道具沿已建立的路线前进。另一人的路线与之并行，保持道具两端和同伴的间距可见。",
          "The character follows an established path with the long prop. Their partner takes a parallel path. Keep the separation between the prop and the partner visible."),
         ("道具长枪", "Stage spear")),
        (("枪缨迎风显出方向", "Use the spear tassel to show the wind"),
         ("远景中人物从旗阵旁穿过，人物的衣摆与枪缨随同一阵风扬起。切近景时保留风向、步态与枪缨的幅度。",
          "In a wide shot, the character moves past the banners. Their coat and the spear tassel lift in the same gust. Match the wind direction, stride, and tassel movement in the closer shot."),
         ("带缨道具长枪", "Stage spear with a tassel")),
    ),
    ("剑道具", "Stage swords"): (
        (("剑尖余光过渡", "Transition on the sword's glow"),
         ("上一格的幻想光效已经开始消退。下一格的剑道具停在同一位置，光线从剑面慢慢映到手背后熄下。",
          "The fantasy glow begins to fade in the first panel. The prop stays in position as the last light moves onto the back of the hand and goes dark."),
         ("道具剑", "Stage sword")),
        (("剑身映出画外灯", "Reveal an offscreen light in the sword"),
         ("灯亮后人物才转目看向亮点，剑身上出现对应方向的反光。镜头保留同一持物手与光的来向。",
          "The light comes on before the character looks toward it. Its reflection appears on the sword. Keep its direction and the holding hand readable."),
         ("道具剑", "Stage sword")),
        (("剑与护手停在同一构图", "Hold on the sword and hand"),
         ("人物动作收住后，镜头从肩部落向手和道具。切近景时护手朝向、手的位置和袖口状态都延续。",
          "After the movement settles, shift attention from the shoulder to the hand and prop. Match the guard orientation, hand position, and sleeve in the close-up."),
         ("道具剑", "Stage sword")),
        (("剑道具交回架上", "Return the sword to its stand"),
         ("人物走到已建立的道具架前，放稳后把手抽离。末镜同时看见接触点、道具朝向和人物离开的方向。",
          "The character reaches the established stand, sets the sword in place and withdraws their hand. End on the contact point, prop orientation, and exit direction."),
         ("道具剑", "Stage sword")),
        (("剑鞘入画接背影", "Match the scabbard into a rear view"),
         ("人物转身时道具剑鞘从身体侧边进入画面。下一机位接同一侧的剑鞘和衣摆运动，再展示离开的背影。",
          "The scabbard comes into view as the character turns. Match its side and the clothing movement before revealing the departing rear view."),
         ("道具剑与剑鞘", "Stage sword and scabbard")),
        (("漂浮剑影汇合成一柄", "Merge floating sword images into one"),
         ("人物经过幻境中的浮动剑影，快到出口时几道剑影在身侧重合。下格只保留同侧的一柄实体道具与消退的残光。",
          "The character passes through floating sword images. Near the exit the images converge at their side. The next panel shows one physical prop on that side and the last fading glow."),
         ("道具剑", "Stage sword")),
    ),
    ("戟道具", "Stage halberds"): (
        (("戟的剪影预示来人", "Announce an arrival with a halberd silhouette"),
         ("长柄戟的轮廓先投上城门，人物随后进入光源方向一致的区域。保留戟头可辨轮廓与固定门框。",
          "The halberd silhouette reaches the gate before the character enters the same light. Keep its distinctive outline and the fixed gate frame visible."),
         ("道具戟", "Stage halberd")),
        (("举起后顶端仍在画内", "Keep the halberd head in frame"),
         ("人物在已建立的地面标记处停稳。道具升起后定住，取景从全身稍移到道具上端与表情同框。",
          "The character settles on an established floor mark. As the prop rises and holds, reframe to keep its head and the expression together."),
         ("道具戟", "Stage halberd")),
        (("戟过台阶保持高低关系", "Carry a halberd past a step"),
         ("人物沿台阶边缘移动，画面同时交代脚下的新高度和长柄的方向。下镜保留台阶与道具的相对关系。",
          "Follow the character along the step. Show the new foot height and the direction of the shaft. Match both against the step in the next shot."),
         ("道具戟", "Stage halberd")),
        (("戟头挂饰停摆", "Let the halberd ornament settle"),
         ("人物已经停下，挂饰还轻摆一拍再安静。切点落在晃动停止时，给下一格明确的静止状态。",
          "The character has stopped while the ornament sways for one more beat. Cut once it settles to establish a clear resting state."),
         ("带挂饰的道具戟", "Stage halberd with ornament")),
        (("长柄戟交接道具位", "Handoff at the marked prop position"),
         ("两位人物在固定标记两侧，先交代谁扶住了长柄。交接完成时留一道清楚的轮廓，并标出新的持有人。",
          "Place the two characters on opposite sides of the mark. Establish who is supporting the long shaft, then hold on the new owner and the clear prop silhouette."),
         ("道具戟", "Stage halberd")),
        (("雾中亮起戟头轮廓", "Light the halberd silhouette through fog"),
         ("人物走过雾带，背景远灯依次照亮戟头和人物的肩部。人物停在雾带外，下格保持亮侧、间距和角色脚下的位置。",
          "The character crosses a bank of fog. A distant light picks out the halberd head, then the character's shoulder. Match the lit side, separation, and floor position once they stop beyond the fog."),
         ("道具戟", "Stage halberd")),
    ),
    ("扇、棍与盾", "Fans, staffs & shields"): (
        (("扇面打开显露眼神", "Reveal a gaze as the fan opens"),
         ("扇面在下半张脸前打开，眼神越过扇面边缘看向对方。下一格保留扇面开合状态与视线方向。",
          "The fan opens across the lower face. The gaze moves above its edge toward the partner. Match the fan's open state and eye line in the next panel."),
         ("折扇", "Folding fan")),
        (("合扇后让出面部", "Close the fan to reveal the face"),
         ("折扇合拢并从脸前移到身侧，人物的表情完全露出。切点选在脸和合拢道具同时可见的位置。",
          "The fan closes and moves from the face to the character's side. Cut with both the revealed expression and the closed prop visible."),
         ("折扇", "Folding fan")),
        (("长棍带出机位移动", "Follow a staff to reveal the space"),
         ("镜头沿前景长棍的轮廓移动，最后落到人物与门框同画的位置。长棍和人物在空间里有固定落点。",
          "Track the foreground staff outline until the character and doorway share the frame. Keep both the person and the staff anchored in the scene."),
         ("道具长棍", "Stage staff")),
        (("长棍从画面边缘移走", "Clear a staff from the frame edge"),
         ("人物将靠在墙边的长棍带走，露出原来被遮住的门牌。下一镜用门牌和空出的位置确认变化。",
          "The character collects the staff from the wall, revealing a sign it covered. Use the sign and newly empty space to match the next shot."),
         ("道具长棍", "Stage staff")),
        (("盾边让出同伴的脸", "Reveal a partner from behind a shield"),
         ("人物移动盾道具后，同伴的脸从轮廓边缘出现。两个角色的站位和看向何处能在同一格读清。",
          "As the shield shifts, the partner's face appears beside its edge. Keep both positions and their lines of sight clear in one panel."),
         ("道具盾", "Stage shield")),
        (("盾靠墙露出路牌", "Rest the shield and reveal the sign"),
         ("人物把盾立到指定墙边，露出身后的路牌。停一拍确认盾面朝向和路牌内容，供下一镜定位。",
          "The character rests the shield by the wall, revealing the sign behind them. Hold to establish the shield's orientation and the sign for the next shot."),
         ("道具盾", "Stage shield")),
    ),
    ("现代影视道具", "Modern screen props"): (
        (("枪形道具留在支架", "Leave a prop firearm on its stand"),
         ("人物走出画面前把枪形道具放回固定支架。近景记下手离开后道具的位置和支架上的编号。",
          "Before exiting, the character returns the prop firearm to its stand. Hold on its position and the stand's label after the hand leaves."),
         ("影视枪形道具", "Prop firearm")),
        (("携带枪形道具走过门框", "Carry a prop firearm past a doorway"),
         ("人物携带道具步过门框，取景重点是走向、持物手和服装状态。下镜从同方向接人物离开。",
          "The character crosses the doorway carrying the prop. Frame the travel direction, holding hand, and clothing. Match the exit direction in the next shot."),
         ("影视枪形道具", "Prop firearm")),
        (("对讲机入画接声音", "Bring a radio into frame before speaking"),
         ("对讲机进入胸前的可见区域，人物抬眼后再开口。镜头结束时保留设备位置，下一镜接画外回应。",
          "The radio comes into view near the chest. The character raises their eyes before speaking. Hold its position before cutting to the offscreen response."),
         ("道具对讲机", "Prop radio")),
        (("拎箱进场放到标记", "Carry a case to its mark"),
         ("人物拎箱到地面标记处，箱底先落地，手再离开把手。下一格交代箱上的编号与原朝向。",
          "The character carries the case to its floor mark. The case settles before the hand releases the handle. Match its label and orientation in the next panel."),
         ("道具箱", "Prop case")),
        (("手机光把视线带过去", "Let a phone's glow draw the gaze"),
         ("手机亮屏后，人物先被光吸引，再转向身旁等回应的人。镜尾留下同一只持机手和两人的视线关系。",
          "The phone lights up, drawing the gaze before the character turns to the waiting partner. End on the same holding hand and readable eye lines."),
         ("道具手机", "Prop phone")),
    ),
}


_CATEGORY_IDS = {
    ("日常与表演", "Everyday & performance"): "performance",
    ("双人配合与救援", "Partner movement & rescue"): "partners",
    ("路线、遮挡与转场", "Paths, occlusion & transitions"): "paths",
    ("刀道具", "Stage sabers"): "sabers",
    ("长枪道具", "Stage spears"): "spears",
    ("剑道具", "Stage swords"): "swords",
    ("戟道具", "Stage halberds"): "halberds",
    ("扇、棍与盾", "Fans, staffs & shields"): "stage",
    ("现代影视道具", "Modern screen props"): "modern",
}
# Assign IDs explicitly to each shipped title so a reorder never changes
# saved cards or their link to the bundled preview.
_KEYS = {
    "performance": {
        "推门后等一拍": "01", "起身时发现异样": "02", "递出后松手": "03",
        "停步侧耳": "04", "放下杯子才开口": "05", "转身前犹豫": "06",
    },
    "partners": {
        "伸手得到回应": "01", "一人扶起另一人": "02", "护送通过门洞": "03",
        "两人架着大箱让路": "04", "前人示意后人停下": "05", "交接手电照明": "06",
    },
    "paths": {
        "从柱后走入光里": "01", "经过前景遮挡切镜": "02", "踩过门槛回身看": "03",
        "借栏杆停住": "04", "逆光里换成前景视角": "05", "避开落下的布景": "06",
    },
    "sabers": {
        "灯光扫过道具刀": "01", "刀停在桌沿": "02", "刀影进入墙上": "03",
        "刀道具让位给表情": "04", "放下后退到光外": "05", "刀光划过前景转场": "06",
    },
    "spears": {
        "枪杆先露出转角": "01", "长枪靠到固定墙边": "02", "长枪过窄门": "03",
        "枪尾留下固定触点": "04", "并行走位保留间距": "05", "枪缨迎风显出方向": "06",
    },
    "swords": {
        "剑尖余光过渡": "01", "剑身映出画外灯": "02", "剑与护手停在同一构图": "03",
        "剑道具交回架上": "04", "剑鞘入画接背影": "05", "漂浮剑影汇合成一柄": "06",
    },
    "halberds": {
        "戟的剪影预示来人": "01", "举起后顶端仍在画内": "02", "戟过台阶保持高低关系": "03",
        "戟头挂饰停摆": "04", "长柄戟交接道具位": "05", "雾中亮起戟头轮廓": "06",
    },
    "stage": {
        "扇面打开显露眼神": "01", "合扇后让出面部": "02", "长棍带出机位移动": "03",
        "长棍从画面边缘移走": "04", "盾边让出同伴的脸": "05", "盾靠墙露出路牌": "06",
    },
    "modern": {
        "枪形道具留在支架": "01", "携带枪形道具走过门框": "02", "对讲机入画接声音": "03",
        "拎箱进场放到标记": "04", "手机光把视线带过去": "05",
    },
}


@dataclass(frozen=True)
class ActionPreset:
    id: str
    category: tuple[str, str]
    title: tuple[str, str]
    movement: tuple[str, str]
    prop: tuple[str, str]


ACTION_PRESETS = tuple(
    ActionPreset(f"{_CATEGORY_IDS[category]}-{_KEYS[_CATEGORY_IDS[category]][title[0]]}",
                 category, title, movement, prop)
    for category, records in PRESETS.items()
    for title, movement, prop in records
)
_BY_KEY = {preset.id: preset for preset in ACTION_PRESETS}
_BY_LEGACY_TEXT = {
    (preset.title[language], preset.movement[language], preset.prop[language]): preset
    for preset in ACTION_PRESETS for language in range(2)
}


def get_preset(preset_id: str) -> ActionPreset | None:
    return _BY_KEY.get(preset_id)


def find_legacy_preset(title: str, movement: str, prop: str) -> ActionPreset | None:
    return _BY_LEGACY_TEXT.get((title, movement, prop))


def action_preview_path(preset_id: str) -> Path | None:
    if preset_id in _BY_KEY:
        return Path(__file__).resolve().parents[1] / ACTION_PREVIEW_DIRECTORY / f"{preset_id}.webp"
    return None
