from pathlib import Path

import pytest
from PIL import Image

from src.batch_planning import coverage_issues
from src.batch_revision import revise_episode
from src.batch_workspace import BatchWorkspace
from src.production_project import ProductionProject
from src.production_rules import CHINESE


def test_version_changes_only_affected_group_work_and_keeps_old_draft(tmp_path):
    w = BatchWorkspace.create(tmp_path / '季.cfbatch', '季', CHINESE)
    script = '\n'.join(f'庭院里的灯依次亮起，第{i}个窗口映出树影。' for i in range(22))
    w.add_episode('EP01', '第一集', script)
    initial = w.group_paths('EP01')
    assert len(initial) >= 2
    selected = initial[-1]
    saved = ProductionProject.open(selected)
    saved.shots[0].fields['连续性'] = '树在画面左侧'
    picture = tmp_path / '庭院.png'
    Image.new('RGB', (80, 45), 'green').save(picture)
    saved.import_image(selected, picture, picture.name, action='新生成', reason='窗外', inspection='树影', reference_only=True)
    saved.save(selected)
    w.require_asset('EP01', selected.stem, '庭院', '雨后', 'R1')
    w.approve_plan('EP01')

    new = tmp_path / '修订稿.txt'
    new.write_text(script.replace('第0个窗口', '第一扇窗'), encoding='utf-8')
    result = revise_episode(w, 'EP01', new)
    assert result['version'] == 'R2' and result['changed'] == [initial[0].stem]
    assert selected.stem in result['reused']
    assert (Path(result['archive'])/'episode-plan.json').exists() and selected.is_file()
    later = w.group_paths('EP01')
    updated = ProductionProject.open(later[-1])
    assert updated.shots[0].fields['连续性'] == '树在画面左侧'
    assert updated.checked_image(later[-1], updated.images[0]).read_bytes() == picture.read_bytes()
    assert len(w.required_assets('EP01', selected.stem)) == 1 and not w.plan_approved('EP01')
    assert coverage_issues(w.plan_for('EP01'), [ProductionProject.open(p) for p in later]) == []
    assert not revise_episode(w, 'EP01', new)['changed']
    assert later == w.group_paths('EP01')
    new.write_text('  ', encoding='utf-8')
    with pytest.raises(ValueError):
        revise_episode(w, 'EP01', new)
    assert later == w.group_paths('EP01')


def test_revision_moves_explicit_passage_cuts_with_verbatim_text(tmp_path):
    w = BatchWorkspace.create(tmp_path / 'test.cfbatch', '示例', CHINESE)
    source = '门打开。\r\n她停在窗前，抬眼看向庭院。\r\n'
    w.add_episode('EP01', '第一集', source)
    p = w.plan_for('EP01')['passages'][-1]
    w.split_passage('EP01', p['id'], [p['start']+6])
    before = w.plan_for('EP01')
    output = tmp_path/'new.txt'
    output.write_bytes(source.replace('门打开', '大门缓缓打开').encode('utf-8'))
    revise_episode(w, 'EP01', output)
    after = w.plan_for('EP01')
    assert after['source_text'] == output.read_bytes().decode('utf-8')
    assert after['shot_splits'][p['id']] == [after['passages'][-1]['start']+6]
    assert [s['text'] for s in after['shots'][-2:]] == [s['text'] for s in before['shots'][-2:]]
