"""Link production stages through the project and its stable source IDs."""

import re

from .production_project import ProductionProject


def attach_script(path, title, text, rules, *, existing):
    """Use this exact manuscript as a source without overwriting a revision."""
    if existing:
        project = ProductionProject.open(path)
    else:
        if path.exists():
            raise ValueError("这个项目文件已存在，请选择新文件名。")
        project = ProductionProject(path.stem, "EP01", "SB01", rules=rules)

    matching = [item for item in project.sources if item.name == title]
    for source in matching:
        if source.text == text:
            return project, source

    revisions = [int(match[1]) for item in matching if (match := re.fullmatch(r"R([0-9]+)", item.version, re.I))]
    source = project.import_source(title, f"R{max(revisions, default=0) + 1}", text)
    project.save(path)
    return project, source


def shot_sources(project):
    """Return approved sources referenced by the current group, in project order."""
    referenced = {item.source for item in project.shots}
    sources = tuple(item for item in project.sources if item.id in referenced)
    if not sources or referenced != {source.id for source in sources}:
        raise ValueError("请先在镜头清单中为每个镜头绑定批准剧本。")
    return sources


def asset_shot_context(project, source):
    """Use only active shots bound to this version; leave manual anchors unparsed."""
    last_line = len(source.text.splitlines())
    context = []
    fields = ("画面/事件", "动作起止", "人物站位", "唯一角色数量锁定", "连续性", "场景/环境")
    for index, shot in enumerate(project.shots, 1):
        if shot.source != source.id:
            continue
        item = {"shot_id": shot.id, "number": f"{project.group}-{index:02d}",
                "description": shot.anchor, "scene": shot.scene,
                "fields": {key: shot.fields[key] for key in fields if shot.fields.get(key)}}
        match = re.fullmatch(r"剧本第 ([0-9]+)–([0-9]+) 行", shot.anchor)
        if match and 1 <= int(match[1]) <= int(match[2]) <= last_line:
            item["script_line_span"] = [int(match[1]), int(match[2])]
        context.append(item)
    return tuple(context)
