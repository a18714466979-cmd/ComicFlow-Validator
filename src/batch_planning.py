"""Source-anchored, editable episode plans. Draft beats never imply visual approval."""

import re
from collections import Counter
from copy import deepcopy
from hashlib import sha256

from assets.workflow_validators.english.plan_english_dialogue import MAX_ENGLISH_WORDS, english_word_count
from .production_project import PARENT_SHOT_FIELD, ApprovedLine, ApprovedSource, ProductionProject, Shot
from .production_rules import CHINESE, ENGLISH
from .storyboard_preflight import CHINESE_SPEECH_LIMIT, chinese_breaks, chinese_speech_length


SCENE = re.compile(r"^(?:EP[0-9]+[-_ ]SC[0-9]+\b|(?:INT\.?/EXT\.?|INT\.|EXT\.|I/E\.)\s|(?:场景|地点|场次|Scene|Location)\s*[:：]|第[零一二三四五六七八九十百\d]+场|(?:内景|外景)[\s·:：—-])", re.I)
LOCATION = re.compile(r"(?:家中|[\u3400-\u9fff]{0,10}(?:家中|家里|卧室|客厅|办公室|会议室|接待室|病房|教室|酒吧|更衣室|走廊|厨房))$")
TRANSITION = re.compile(r"^转场[（(]([^()（）]+)[）)]")
TONE = re.compile(r"(?:[（(](?:无奈|冷哼|哭|低声|压低声音|轻声|喊|笑|叹气|被打断)[）)]|无奈|冷哼|低声道|低声说|笑道|怒道)$")
SCREENPLAY_SPEAKER = re.compile(r"^[A-Z][A-Z'’.-]*(?: [A-Z][A-Z'’.-]*){0,2}(?: \((?:V\.O\.|O\.S\.|CONT'D)\))?$")
SOUND_CUE = re.compile(r"(?:[（(](V\.?O\.?|O\.?S\.?|画外音|内心|旁白|电话音|无线电)[）)]|(?<=[\u3400-\u9fff ])(V\.?O\.?|O\.?S\.?))$", re.I)
VOICE_ONLY = {"旁白", "画外音", "广播", "系统音", "narrator", "announcement"}
STAGE_DIRECTION = re.compile(r"[（(](?:被打断|停顿|压低声音|轻声|低声|哽咽|whispering|quietly|pause|beat|interrupted)[）)]", re.I)
UNSPOKEN_SUFFIX = re.compile(r"(?:[（(](?:被打断|被截断|停顿|欲言又止|压低声音|低声|叹气|哽咽|interrupted|pause)[）)])+\s*$", re.I)
PROJECT_NOTE = re.compile(r"^(?:来源[:：]|原场\s|.*修订稿[｜|]|英文为表演对白|[A-Z0-9 :’'-]+\sEP\d+\s*$|(?:-{3,}|_{3,})$)")
EPISODE = re.compile(r"^(?:第[零一二三四五六七八九十百\d]+集|EP(?:ISODE)?\s*\d+)\b", re.I)
DIALOGUE = re.compile(r"(?P<speaker>[\w\u3400-\u9fff][\w\u3400-\u9fff .’'()（）·-]{0,35}?)\s*[:：]\s*(?P<body>\S.*)")
ACTION_LABELS = {"动作", "画面", "镜头", "场面", "音效", "字幕", "特效", "说明", "action", "shot", "sfx", "camera", "cut to"}
ASSET_LABELS = {"人物": "人物", "角色": "人物", "character": "人物", "道具": "道具", "props": "道具", "prop": "道具"}
QUOTES = {"“": "”", "「": "」", "『": "』", '"': '"', "‘": "’"}


def _marked_content(line):
    return re.sub(r"^(?:#{1,6}\s+|[-*]\s+|\d+[.)]\s+)", "", line.lstrip("\ufeff \t"), count=1).strip()


def _utterance(raw, clean):
    # Keep the physical-source offsets even when Markdown marks up the speaker.
    candidate = re.sub(r"^\*\*([^*]+?)\*\*\s*([:：])", r"\1\2", clean)
    candidate = re.sub(r"^\*\*([^*]+?[:：])\*\*\s*", r"\1 ", candidate)
    match = DIALOGUE.fullmatch(candidate)
    if not match:
        return "", "", 0
    speaker = match["speaker"].strip()
    body = match["body"].strip()
    offset = raw.rfind(body)
    body = UNSPOKEN_SUFFIX.sub("", body).rstrip()
    leading_cue = STAGE_DIRECTION.match(body)
    if leading_cue:
        offset += leading_cue.end()
        body = body[leading_cue.end():]
        offset += len(body) - len(body.lstrip())
        body = body.lstrip()
    if body and body[0] in QUOTES and body[-1] == QUOTES[body[0]] and len(body) > 1:
        body = body[1:-1]
        offset += 1
    offset += len(body) - len(body.lstrip())
    return speaker, body.strip(), offset


def _english_ends(body):
    cuts = []
    for match in re.finditer(r"""[.!?]+['”"’)]*\s+(?=\S)""", body):
        before = body[:match.start()]
        if match[0].startswith(".") and re.search(r"(?:\b(?:Mr|Ms|Mrs|Dr|St|Prof|Jr|Sr|vs|etc)|\b[A-Z]|(?:\b[A-Za-z]\.)+[A-Za-z])$", before):
            continue
        cuts.append(match.end())
    return (*cuts, len(body))


def _speech_units(body, rules):
    if rules == ENGLISH:
        return _english_ends(body)
    ends = []
    start = 0
    for end in chinese_breaks(body):
        if chinese_speech_length(body[start:end]) > CHINESE_SPEECH_LIMIT:
            ends.extend(start + match.end() for match in re.finditer(r"[，,；;：:、]+\s*(?=\S)", body[start:end]))
        ends.append(end)
        start = end
    return tuple(ends)


def _speech_count(text, rules):
    return chinese_speech_length(text) if rules == CHINESE else english_word_count(text)


def _cap(rules):
    return CHINESE_SPEECH_LIMIT if rules == CHINESE else MAX_ENGLISH_WORDS


def _spec(shots):
    count = len({span[0] for shot in shots for span in shot["dialogue"]})
    if not count:
        return "无对白", 9
    if count > 2:
        return "三句以上或长对白", 6
    return "1-2句短对白", 8


def _line_passages(text):
    position = 0
    for index, physical in enumerate(text.splitlines(keepends=True), 1):
        raw = physical.rstrip("\r\n")
        if raw.strip():
            yield index, raw, position
        position += len(physical)


def _digest(*parts):
    return sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def plan_episode(name, episode, source_name, text, rules, *, version="R1", shot_splits=None):
    if rules not in (ENGLISH, CHINESE):
        raise ValueError("请选择英文或中文影片制作规则。")
    if not isinstance(text, str) or not text.strip() or "\0" in text:
        raise ValueError("剧本为空或不是有效文本。")
    if any(not isinstance(s, str) or not s.strip() or any(c in s for c in "\r\n|\0") for s in (name, episode, source_name, version)):
        raise ValueError("项目名、集号、稿名和版本须为有效单行文本。")
    source_id = _digest(name, episode, source_name, version, text)
    if shot_splits is None:
        shot_splits = {}
    if not isinstance(shot_splits, dict):
        raise ValueError("源段切点须按源段 ID 登记。")
    matched_cuts = set()
    plan = {"name": name, "episode": episode, "source_name": source_name, "source_text": text,
            "source_id": source_id, "version": version, "rules": rules, "passages": [], "shots": [],
            "lines": [], "assets": [], "issues": [], "groups": [], "shot_splits": deepcopy(shot_splits)}
    scene = ""
    occurrences = Counter()
    pending_assets = []
    standalone_speaker = ""


    def add_shot(passage, start, end, dialogue, weight):
        sid = _digest(episode, passage["id"], str(start - passage["start"]))
        shot = {"id": sid, "passage_id": passage["id"], "line_no": passage["line_no"],
                "scene": scene, "start": start, "end": end, "text": text[start:end],
                "line_id": dialogue[0][0] if dialogue else "", "speaker": passage["speaker"],
                "dialogue": dialogue, "spoken_count": weight, "assets": list(pending_assets)}
        if scene:
            shot["assets"].append("场景：" + scene)
        shot["cue"] = passage.get("cue", "")
        if passage["speaker"] and not shot["cue"] and passage["speaker"].casefold() not in VOICE_ONLY:
            shot["assets"].append("人物：" + passage["speaker"])
        pending_assets.clear()
        passage["shot_ids"].append(sid)
        plan["shots"].append(shot)

    physical = list(_line_passages(text))
    for passage_pos, (idx, raw, pos) in enumerate(physical):
        clean = _marked_content(raw)
        occurrences[raw] += 1
        pid = "P" + _digest(episode, raw, str(occurrences[raw]))[:16]
        p = {"id": pid, "text": raw, "start": pos, "end": pos + len(raw), "line_no": idx,
             "kind": "action", "speaker": "", "scene": scene, "shot_ids": []}
        plan["passages"].append(p)
        if SCENE.match(clean) or LOCATION.fullmatch(clean):
            scene = re.sub(r"^(?:场景|地点|场次|Scene|Location)\s*[:：]\s*", "", clean, flags=re.I)
            scene = re.sub(r"^EP[0-9]+[-_ ]SC[0-9]+\s+", "", scene, flags=re.I)
            p.update(kind="scene", scene=scene)
            standalone_speaker = ""
            continue
        if (EPISODE.match(clean) or re.match(r"^《[^》]+》\s*第[零一二三四五六七八九十百\d]+集", clean)
                or raw.lstrip().startswith("#") or PROJECT_NOTE.match(clean)):
            p["kind"] = "heading"
            continue
        if rules == ENGLISH and re.match(r"^(?:中文译文|中文翻译|译文)\s*[:：]", clean):
            p["kind"] = "translation"
            continue
        transition = TRANSITION.match(clean)
        if transition:
            scene = transition[1].strip()
            p["scene"] = scene
        if not clean:
            p["kind"] = "heading"
            continue
        speaker, body, offset = _utterance(raw, clean)
        if standalone_speaker and not speaker and re.fullmatch(r"\([^()]+\)|（[^（）]+）", clean):
            p["kind"] = "direction"
            continue
        if standalone_speaker and not speaker:
            speaker, body, offset = standalone_speaker, clean, raw.find(clean)
        standalone_speaker = ""
        if (rules == ENGLISH and not speaker and SCREENPLAY_SPEAKER.fullmatch(clean)
                and clean not in {"DAY", "NIGHT", "THE END", "FADE OUT", "FADE IN", "INT.", "EXT."}
                and passage_pos + 1 < len(physical)):
            following = _marked_content(physical[passage_pos + 1][1])
            if not (SCENE.match(following) or DIALOGUE.fullmatch(following) or following.isupper()):
                p["kind"] = "speaker"
                standalone_speaker = clean
                continue
        voice = SOUND_CUE.search(speaker)
        if voice and voice.start():
            p["cue"] = voice[1] or voice[2]
            speaker = speaker[:voice.start()].strip()
        if speaker.casefold() in ASSET_LABELS:
            p["kind"] = "assets"
            for item in re.split(r"[、,，]", body):
                if item.strip():
                    pending_assets.append(ASSET_LABELS[speaker.casefold()] + "：" + item.strip())
            continue
        if TONE.search(speaker):
            speaker = TONE.sub("", speaker).strip()
        if speaker.casefold() in ACTION_LABELS or speaker.endswith(("的画面", "的场景", "的声音")):
            speaker = ""
        if not speaker:
            if clean.startswith(tuple(QUOTES)):
                plan["issues"].append(f"第 {idx} 行有引述但缺少说话人；请用「姓名：对白」标明原稿或确认其为动作描述。")
            cuts = shot_splits.get(pid, [])
            if pid in shot_splits:
                matched_cuts.add(pid)
            if (not isinstance(cuts, list) or any(type(cut) is not int for cut in cuts)
                    or cuts != sorted(set(cuts)) or any(not pos < cut < p["end"] for cut in cuts)):
                raise ValueError(f"第 {idx} 行的源段切点须位于原文内部并按顺序排列。")
            if any(re.fullmatch(r"[A-Za-z0-9]{2}", text[cut-1:cut+1]) for cut in cuts):
                raise ValueError(f"第 {idx} 行的切点会截断单词，请选择两个叙事动作之间的位置。")
            for left, right in zip([pos, *cuts], [*cuts, p["end"]]):
                if cuts and not re.search(r"\w", text[left:right]):
                    raise ValueError(f"第 {idx} 行的每个新镜头都须保留实际动作原文。")
                add_shot(p, left, right, [], 0)
            continue
        p.update(kind="dialogue", speaker=speaker)
        if not body:
            plan["issues"].append(f"第 {idx} 行的对白缺少实际原文。")
            continue
        if STAGE_DIRECTION.search(body):
            plan["issues"].append(f"第 {idx} 行含内嵌表演提示。请把提示移到独立动作行，并分别保留其前后批准对白。")
        if rules == ENGLISH and re.search(r"[\u3400-\u9fff]", body):
            plan["issues"].append(f"第 {idx} 行含中文发声文字。请核对所选制作规则和批准稿语言。")
        base = pos + offset
        ends = _speech_units(body, rules)
        line_id = "D" + pid[1:]
        if rules == CHINESE:
            plan["lines"].append({"id": line_id, "speaker": speaker, "text": body, "sentence_ends": list(ends)})
        start, shot_start, spans, weight = 0, 0, [], 0
        for ordinal, end in enumerate(ends, 1):
            piece = body[start:end]
            count = _speech_count(piece, rules)
            if count > _cap(rules) or not count:
                plan["issues"].append(f"第 {idx} 行 [{start}:{end}] 发声量 {count}，请核对批准的句界或原稿；本组上限 {_cap(rules)}。")
            if spans and weight + count > _cap(rules):
                add_shot(p, base + shot_start, base + start, spans, weight)
                shot_start, spans, weight = start, [], 0
            if rules == ENGLISH:
                part_id = line_id if len(ends) == 1 else f"{line_id}_{ordinal}"
                original = piece.strip()
                span = [part_id, 0, len(original)]
                plan["lines"].append({"id": part_id, "speaker": speaker, "text": original, "sentence_ends": [len(original)]})
                spans.append(span)
            elif spans:
                spans[-1][2] = end
            else:
                spans.append([line_id, start, end])
            start, weight = end, weight + count
        if spans:
            add_shot(p, base + shot_start, base + len(body), spans, weight)
    if matched_cuts != shot_splits.keys():
        raise ValueError("切点需要对应当前源稿中的动作段。对白按制作规则在批准句界分配。")
    if pending_assets:
        plan["assets"].extend(pending_assets)
    if not plan["shots"]:
        plan["issues"].append("未找到可编排的剧情或对白。请补充有实际内容的源段。")
    groups = _draft_groups(plan["shots"], rules)
    _assign_groups(plan, groups)
    plan["assets"] = list(dict.fromkeys([*(asset for g in plan["groups"] for asset in g["assets"]), *plan["assets"]]))
    return plan


def split_passage(plan, passage_id, offsets):
    """Replace one action passage's cut list with approved absolute character positions."""
    passage = next((p for p in plan["passages"] if p["id"] == passage_id), None)
    if not passage or passage["kind"] != "action":
        raise ValueError("请选择包含动作原文的源段；标题、场标及对白由各自规则处理。")
    if not isinstance(offsets, list):
        raise ValueError("源镜切点需要字符位置列表。")
    cuts = deepcopy(plan.get("shot_splits", {}))
    if offsets:
        cuts[passage_id] = offsets
    else:
        cuts.pop(passage_id, None)
    return plan_episode(plan["name"], plan["episode"], plan["source_name"], plan["source_text"],
                        plan["rules"], version=plan["version"], shot_splits=cuts)


def _draft_groups(shots, rules):
    """Choose legal panel counts globally; keep genuine shortfalls visible for authoring."""
    size = len(shots)
    costs = [(0, 0, 0)] * (size + 1)
    next_cut = [size] * size
    limit = _cap(rules)
    for start in reversed(range(size)):
        best = None
        words = 0
        for end in range(start + 1, min(size, start + 10) + 1):
            words += shots[end - 1]["spoken_count"]
            if words > limit and end > start + 1:
                break
            spec, target = _spec(shots[start:end])
            panels = end - start
            maximum = 10 if spec == "无对白" else target
            if panels > maximum:
                continue
            deficit = max(0, target - panels) if end < size else 0
            # A documented English speech-overflow group may be shorter than the usual target.
            if (rules == ENGLISH and words and end < size
                    and words + shots[end]["spoken_count"] > limit):
                deficit = 0
            # Prefer fewer underfilled groups first, then fewer groups, then a cut at a scene change.
            tail = costs[end]
            break_scene = int(end < size and shots[end - 1]["scene"] == shots[end]["scene"])
            cost = (tail[0] + deficit, tail[1] + 1, tail[2] + break_scene)
            if best is None or cost <= best:
                best, next_cut[start] = cost, end
        costs[start] = best
    groups = []
    start = 0
    while start < size:
        end = next_cut[start]
        groups.append([shot["id"] for shot in shots[start:end]])
        start = end
    return groups


def _assign_groups(plan, groups):
    by_id = {shot["id"]: shot for shot in plan["shots"]}
    plan["groups"] = []
    for index, ids in enumerate(groups, 1):
        shots = [by_id[sid] for sid in ids]
        spec, target = _spec(shots)
        count = sum(s["spoken_count"] for s in shots)
        overflow = 0
        final = index == len(groups)
        if not final and len(shots) < target and count and plan["rules"] == ENGLISH:
            candidate = count + by_id[groups[index][0]]["spoken_count"]
            if candidate > MAX_ENGLISH_WORDS:
                overflow = candidate
        note = ""
        if not final and len(shots) < target and not overflow:
            note = f"当前源镜 {len(shots)} 格，常规目标 {target} 格。请按实际叙事调整相邻组，勿补空镜凑数。"
        plan["groups"].append({"group": f"SB{index:02d}", "planning_note": note, "shot_ids": list(ids),
                               "spoken_count": count, "overflow_candidate": overflow,
                               "dialogue_spec": spec, "target_panels": target,
                               "assets": list(dict.fromkeys(a for s in shots for a in s["assets"]))})


def regroup(plan, groups):
    expected = [s["id"] for s in plan["shots"]]
    if any(not ids for ids in groups) or [sid for ids in groups for sid in ids] != expected:
        raise ValueError("改组须按原稿顺序覆盖全部源镜一次。")
    result = deepcopy(plan)
    _assign_groups(result, groups)
    for group in result["groups"]:
        if group["spoken_count"] > _cap(plan["rules"]):
            raise ValueError(f"{group['group']} 超出所选规则的发声上限。")
        if len(group["shot_ids"]) > max(group["target_panels"], 10 if group["dialogue_spec"] == "无对白" else 0):
            raise ValueError(f"{group['group']} 超出当前对白规格的分组格数。")
    return result


def _anchor(shot):
    return f"剧本第 {shot['line_no']}–{shot['line_no']} 行"


def materialize_group(plan, group_id):
    group = next((g for g in plan["groups"] if g["group"] == group_id), None)
    if group is None:
        raise ValueError(f"计划中没有组 {group_id}。")
    identity = plan["source_id"]
    project = ProductionProject(plan["name"], plan["episode"], group_id, rules=plan["rules"])
    project.sources = [ApprovedSource(identity, plan["source_name"], plan["version"], plan["source_text"])]
    by_id = {s["id"]: s for s in plan["shots"]}
    split_sources = {p["id"] for p in plan["passages"] if len(p["shot_ids"]) > 1}
    scope = {}
    for sid in group["shot_ids"]:
        shot = by_id[sid]
        fields = {"画面/事件": shot["text"]} if not shot["dialogue"] else {}
        if shot["passage_id"] in split_sources:
            fields[PARENT_SHOT_FIELD] = shot["passage_id"]
        if shot.get("cue"):
            fields["声源位置"] = shot["cue"]
        project.shots.append(Shot(id=sid, source=identity, anchor=_anchor(shot), scene=shot["scene"], fields=fields,
                                  dialogue=[tuple(d) for d in shot["dialogue"]]))
        for lid, start, end in shot["dialogue"]:
            scope[lid] = [scope.get(lid, [start])[0], end]
    project.lines = [ApprovedLine(line["id"], line["speaker"], line["text"], identity, tuple(line["sentence_ends"]))
                     for line in plan["lines"] if line["id"] in scope]
    if scope:
        project.dialogue_scope = scope
        if any(start for start, end in scope.values()):
            project.previous_group = f"SB{int(group_id[2:]) - 1:02d}"
    first, last = (by_id[group["shot_ids"][i]]["line_no"] for i in (0, -1))
    final = group_id == plan["groups"][-1]["group"]
    project.notes.update({"覆盖段落": f"剧本第 {first}–{last} 行", "对白规格": group["dialogue_spec"],
                          "分组状态": "整集尾组" if final else "常规"})
    if group["overflow_candidate"]:
        project.notes.update({"分组状态": "对白容量拆组", "对白容量拆组说明":
                              f"{group['overflow_candidate']} | 纳入下一源段的完整对白将超出60词，在原句前换组。"})
    if final:
        project.notes["尾组说明"] = f"已编入本集源稿至第 {last} 行，尾组按实际叙事格数核对。"
    return project


def trace_rows(plan, projects=None):
    """Represent structural lines in the index without adding fictional camera shots."""
    shots = {s["id"]: s for s in plan["shots"]}
    locations = ({sid: (g["group"], number) for g in plan["groups"] for number, sid in enumerate(g["shot_ids"], 1)}
                 if projects is None else {shot.id: (p.group, n) for p in projects for n, shot in enumerate(p.shots, 1)})
    rows = []
    following = next((sid for g in reversed(plan["groups"]) for sid in reversed(g["shot_ids"])), "")
    for p in reversed(plan["passages"]):
        ids = p["shot_ids"]
        if ids:
            following = ids[0]
        for sid in reversed(ids or [following]):
            shot = shots.get(sid, {}) if ids else {}
            group, slot = locations.get(sid, ("", 0))
            rows.append({"passage_id": p["id"], "line_no": p["line_no"], "group": group, "slot": slot,
                         "shot_id": sid, "speaker": p["speaker"], "kind": p["kind"],
                         "line_id": shot.get("line_id", ""), "text": shot.get("text", p["text"]),
                         "start": shot.get("start", p["start"]), "end": shot.get("end", p["end"]),
                         "source_line": p["text"]})
    rows.reverse()
    previous = ""
    for row in rows:
        if row["kind"] in {"action", "dialogue"} and row["shot_id"]:
            previous = row["shot_id"]
        if row["kind"] == "translation" and previous:
            row["shot_id"] = previous
            row["group"], row["slot"] = locations.get(previous, ("", 0))
    return rows


def coverage_issues(plan, projects):
    """Independent full-manuscript check against the actual, reopened group projects."""
    fresh = plan_episode(plan["name"], plan["episode"], plan["source_name"], plan["source_text"],
                         plan["rules"], version=plan["version"], shot_splits=plan.get("shot_splits"))
    issues = list(fresh["issues"])
    for key in ("source_id", "passages", "lines", "shots"):
        if fresh[key] != plan[key]:
            return issues + ["整集源段与锁定剧本不匹配，请重建计划。"]
    expected = [s["id"] for s in plan["shots"]]
    if expected != [sid for g in plan["groups"] for sid in g["shot_ids"]]:
        issues.append("分组清单漏掉、重读或打乱已锁定源镜。")
    if [g["group"] for g in plan["groups"]] != [p.group for p in projects]:
        issues.append("实际项目的组号或顺序与整集清单不符。")
    by_group = {g["group"]: g for g in plan["groups"]}
    approved = ApprovedSource(plan["source_id"], plan["source_name"], plan["version"], plan["source_text"])
    previous = []
    for group in projects:
        if group.group not in by_group:
            continue
        if (group.name, group.episode, group.rules) != (plan["name"], plan["episode"], plan["rules"]):
            issues.append(f"{group.group} 的项目、集号或规则与批次不匹配。")
        if approved not in group.sources:
            issues.append(f"{group.group} 的批准源稿内容或版本已改变。")
        if group.pending_shots:
            issues.append(f"{group.group} 仍有待制作镜头。")
        real_ids = [s.id for s in group.shots]
        previous.extend(real_ids)
        if real_ids != by_group[group.group]["shot_ids"]:
            issues.append(f"{group.group} 的源镜有遗漏、重复、移动或新增，请与整集计划核对。")
        draft = materialize_group(plan, group.group)
        if group.lines != draft.lines:
            issues.append(f"{group.group} 的批准对白原文、身份或说话人已改变。")
        if group.dialogue_scope != draft.dialogue_scope:
            issues.append(f"{group.group} 的批准对白范围已改变。")
        targets = {shot.id: shot for shot in draft.shots}
        for shot in group.shots:
            target = targets.get(shot.id)
            if target and (target.source != shot.source or target.anchor != shot.anchor):
                issues.append(f"{group.group} / {target.anchor} 的源镜位置已改变。")
            if target and [tuple(x) for x in shot.dialogue] != target.dialogue:
                issues.append(f"{group.group} / {target.anchor} 的发声片段与批准原文不符。")
    if previous != expected:
        issues.append("实际镜头未按原稿顺序覆盖整集一次。")
    return list(dict.fromkeys(issues))
