"""Update an episode manuscript while preserving unaffected group work and the old revision."""

import json
import re
from dataclasses import replace
from pathlib import Path
from shutil import copytree, rmtree

from .asset_registry import sha256_file
from .batch_planning import materialize_group, plan_episode, regroup
from .batch_workspace import _row
from .production_project import ProductionProject, atomic_text


def _compare_groups(plan):
    shots = {s['id']: s for s in plan['shots']}
    # Source line numbers and character offsets can move when an earlier scene is edited.
    return {g['group']: [(sid, shots[sid]['scene'], shots[sid]['text'], shots[sid]['dialogue'],
                          shots[sid]['assets']) for sid in g['shot_ids']] for g in plan['groups']}


def _carry_group(old_path, new_path, original, fresh):
    saved = ProductionProject.open(old_path)
    if (saved.pending_shots or saved.sources != original.sources or saved.lines != original.lines
            or saved.dialogue_scope != original.dialogue_scope or len(saved.shots) != len(original.shots)):
        return False
    for shot, old in zip(saved.shots, original.shots):
        if (shot.id, shot.source, shot.anchor, shot.dialogue) != (old.id, old.source, old.anchor, old.dialogue):
            return False
    for image in saved.images:
        saved.checked_image(old_path, image)
    for suffix in ('.assets', '.candidates'):
        folder = old_path.with_suffix(suffix)
        if folder.is_dir():
            copytree(folder, new_path.with_suffix(suffix))
    new_shots = [replace(shot, source=base.source, anchor=base.anchor)
                 for shot, base in zip(saved.shots, fresh.shots)]
    notes = dict(saved.notes)
    for key in ('覆盖段落', '对白规格', '分组状态', '尾组说明', '对白容量拆组说明'):
        if key in fresh.notes:
            notes[key] = fresh.notes[key]
        else:
            notes.pop(key, None)
    revised = replace(saved, sources=fresh.sources, lines=fresh.lines, previous_group=fresh.previous_group,
                      shots=new_shots, notes=notes, structure_review='', handoffs={})
    revised.save(new_path)
    return True


def revise_episode(workspace, episode_id, input_path):
    path = Path(input_path)
    if path.suffix.lower() not in {'.txt', '.md'}:
        raise ValueError('请选择 UTF-8 TXT 或 Markdown 剧本。')
    source = path.read_bytes().decode('utf-8-sig')
    folder = None
    try:
        with workspace.writing() as db:
            row = _row(db, episode_id)
            previous = json.loads(row['plan'])
            old_files = {p.stem: p for p in workspace._paths(row)}
            if source == previous['source_text']:
                return {'version': previous['version'], 'reused': list(old_files), 'changed': [], 'removed': []}
            revision = re.fullmatch(r'R(\d+)', previous['version'])
            if not revision:
                raise ValueError('旧原稿缺少有效的版本号。')
            plan = plan_episode(workspace.title, row['id'], path.name, source, workspace.rules,
                                version=f'R{int(revision[1])+1}')
            if not plan['shots']:
                raise ValueError('新原稿没有可编排的镜头。')
            # Carry a director's cuts within a verbatim passage even if other edits moved its line.
            if previous.get('shot_splits'):
                old_starts = {p['id']: p['start'] for p in previous['passages']}
                cuts = {p['id']: [cut - old_starts[p['id']] + p['start']
                                  for cut in previous['shot_splits'][p['id']]]
                        for p in plan['passages'] if p['kind'] == 'action' and p['id'] in previous['shot_splits']}
                if cuts:
                    plan = plan_episode(workspace.title, row['id'], path.name, source, workspace.rules,
                                        version=plan['version'], shot_splits=cuts)
            # Preserve the user's cut points if the shot count is stable and the cuts are still legal.
            if len(plan['shots']) == len(previous['shots']):
                ids = iter(s['id'] for s in plan['shots'])
                boundaries = [[next(ids) for _ in group['shot_ids']] for group in previous['groups']]
                try:
                    plan = regroup(plan, boundaries)
                except ValueError:
                    pass  # Different dialogue length or classification needs the new proposed boundaries.
            before, after = _compare_groups(previous), _compare_groups(plan)
            signatures = {group: sha256_file(p) for group, p in old_files.items()}
            folder = workspace._materialize(db, row['id'], row['title'], plan, row['position'])
            reused, changed = [], []
            for group, content in after.items():
                dest = folder / f'{group}.cfproject'
                if before.get(group) == content and _carry_group(
                        old_files[group], dest, materialize_group(previous, group), ProductionProject.open(dest)):
                    reused.append(group)
                else:
                    changed.append(group)
                # Explicit state dependencies follow shared shots across a changed group boundary.
                # Keep an entire replacement at the same group number subject to the prior requirements as well.
                shot_ids = {s[0] for s in content}
                for name, old_content in before.items():
                    if name == group or any(s[0] in shot_ids for s in old_content):
                        db.execute('''INSERT INTO requirements (episode,generation,grp,identity,state,version,deliver)
                            SELECT episode,?,?,identity,state,version,deliver FROM requirements
                            WHERE episode=? AND generation=? AND grp=?
                            ON CONFLICT(episode,generation,grp,identity,state,version)
                            DO UPDATE SET deliver=MAX(requirements.deliver, excluded.deliver)''',
                                   (folder.name, group, row['id'], row['generation'], name))
            if any(sha256_file(old_files[g]) != sha for g, sha in signatures.items()):
                raise ValueError('单组项目正被编辑，请保存后重新更新原稿。')
            old_folder = workspace._folder(row['id'], row['generation'])
            atomic_text(old_folder / 'episode-plan.json', json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
            return {'version': plan['version'], 'reused': reused, 'changed': changed,
                    'removed': [g for g in old_files if g not in after], 'archive': str(old_folder)}
    except BaseException:
        if folder is not None:
            rmtree(folder, ignore_errors=True)
        raise
