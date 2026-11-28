import pytest

from src.camera_preflight import CameraCut, camera_cuts, require_camera_rules
from src.production_project import ProductionProject, Shot
from src.production_rules import CHINESE, ENGLISH


def shot(label, size="", angle="", **fields):
    return label, {"景别": size, "机位/角度": angle, **fields}


def test_chinese_same_scale_aliases_include_cross_group_pairs():
    shots = (
        shot("SB01-10", " 中近景 ", "正侧"),
        shot("SB02-01", "ＭＣＵ", "正面"),
        shot("SB02-02", "近中景", "正面"),
        shot("SB02-03", "特写", "正面"),
    )
    assert camera_cuts(shots, CHINESE) == (
        CameraCut("same_scale", ("SB01-10", "SB02-01"), "中近景"),
        CameraCut("same_scale", ("SB02-01", "SB02-02"), "中近景", "正面"),
    )


def test_english_checks_size_and_angle_and_flags_three_only_if_fighting():
    shots = (
        shot("SB01-01", "中景", "平视", 机位空间="门前"),
        shot("SB01-02", "medium shot", "Eye-level", 机位空间="门后"),
        shot("SB01-03", "MS", "平視", 机位空间="门侧"),
        shot("SB01-04", "中景", "高角度"),
    )
    first = CameraCut("same_framing", ("SB01-01", "SB01-02"), "中景", "平视")
    second = CameraCut("same_framing", ("SB01-02", "SB01-03"), "中景", "平视")
    triple = CameraCut("fight_triple", ("SB01-01", "SB01-02", "SB01-03"), "中景", "平视")
    assert camera_cuts(shots, ENGLISH) == (first, second)
    assert camera_cuts(shots, ENGLISH, fight=True) == (first, second, triple)


def test_missing_values_and_unknown_scale_cannot_create_duplicate_framing():
    shots = (
        shot("01", "未知尺寸", "平视"),
        shot("02", "未知尺寸", "平视"),
        ("03", {}),
        shot("04", "中景", "待核对"),
        shot("05", "中景", "待核对"),
    )
    assert camera_cuts(shots, ENGLISH, fight=True) == ()
    assert camera_cuts(shots, CHINESE) == (CameraCut("same_scale", ("04", "05"), "中景"),)
    assert camera_cuts(shots, "unknown") == ()


def test_active_workflow_rules_reach_drafting_and_board_requests():
    from src.production_drafting import SHOT_TASK, instructions_for
    from src.production_images import image_prompt
    from src.production_project import ProductionProject, Shot
    from src.production_rules import CAMERA_ACTION_FIELD

    assert "相邻独立镜头禁止同景别且同角度" in instructions_for(SHOT_TASK, ENGLISH)
    assert "相邻独立镜头和组间衔接要拉开景别" in instructions_for(SHOT_TASK, CHINESE)
    assert f'"{CAMERA_ACTION_FIELD}"' in instructions_for(SHOT_TASK, CHINESE)
    project = ProductionProject("试用", "EP01", "SB01", rules=CHINESE)
    project.shots.append(Shot(anchor="镜头样例", fields={
        "机位空间": "门左侧", "可见范围": "门把手", CAMERA_ACTION_FIELD: "伸手前切到斜侧",
    }))
    prompt = image_prompt(project, "故事板", "", "文生图")
    assert "相邻独立板格和跨组边界应交叉景别" in prompt
    assert "机位空间 门左侧" in prompt and "可见范围 门把手" in prompt
    assert f"{CAMERA_ACTION_FIELD} 伸手前切到斜侧" in prompt


def test_declared_violations_block_in_both_workflows():
    project = ProductionProject("检查", "EP01", "SB01")
    project.shots = [
        Shot(fields={"景别": "中景", "机位/角度": angle, "本格新增叙事功能": "确认门已关闭"})
        for angle in ("平视", "高角度")
    ]
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        require_camera_rules(project)
    project.shots[1].fields["本格新增叙事功能"] = "确认窗闩仍锁着"
    require_camera_rules(project)
    project.notes["内容类型"] = "纯打斗"
    project.shots = [Shot(fields={"景别": size, "机位/角度": angle}) for size, angle in
                     (("中景", "平视"), ("MS", "Eye-level"), ("medium shot", "平視"))]
    with pytest.raises(ValueError, match="SB01-01 → SB01-02 → SB01-03"):
        require_camera_rules(project)
    project.rules = CHINESE
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        require_camera_rules(project)


def test_english_formal_board_checks_group_before_img_request():
    from src.production_export import check_english_board_input

    project = ProductionProject("检查", "EP01", "SB01")
    project.notes = {"分组状态": "常规", "对白规格": "无对白", "内容类型": "其他"}
    project.shots = [Shot() for _ in range(8)]
    with pytest.raises(ValueError, match="9、10"):
        check_english_board_input(project, None)
    project.shots.append(Shot())
    with pytest.raises(ValueError, match="SB01-01.*唯一角色数量锁定"):
        check_english_board_input(project, None)
    for index, shot_entry in enumerate(project.shots, 1):
        shot_entry.fields.update({"景别": "中近景" if index % 2 else "特写", "机位/角度": "斜侧", "机位空间": "窗边",
                                  "可见范围": "窗台", "画面/事件": "窗闩移动", "人物站位": "无",
                                  "动作起止": "窗闩回位", "唯一角色数量锁定": "无",
                                  "本格新增叙事功能": f"第 {index} 处窗闩回位"})
    check_english_board_input(project, None)
    project.notes["分组状态"] = "整集尾组"
    with pytest.raises(ValueError, match="实际结尾说明"):
        check_english_board_input(project, None)
    project.notes["尾组说明"] = "故事在玻璃杯落到窗台时结束。"
    project.shots = project.shots[:2]
    check_english_board_input(project, None)

@pytest.mark.parametrize("rules", (ENGLISH, CHINESE))
def test_duplicate_framing_rejected_before_adoption_board_request_and_export(tmp_path, rules):
    from src.production_drafting import SHOT_TASK, apply_candidate, build_context
    from src.production_export import build_delivery
    from src.production_images import prepare_job

    project = ProductionProject("门灯", "EP01", "SB01", rules=rules)
    source = project.import_source("剧本.txt", "V1", "灯亮。\n她转身。")
    first = Shot(source=source.id, anchor="灯亮", fields={"景别": "中景", "机位/角度": "正面"})
    project.shots.append(first)
    context, _ = build_context(project, source, SHOT_TASK, 2, 2)
    fields = {"景别": "MS", "机位/角度": "front view", "本格新增叙事功能": "看见身后的人"}
    candidate = {"task": SHOT_TASK, "context": context, "output": {
        "shots": [{"fields": fields, "line_start": 2, "line_end": 2}]}}
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        apply_candidate(project, candidate, (0,))
    assert project.shots == [first]
    project.shots.append(Shot(source=source.id, anchor="她转身", fields=fields))
    path = tmp_path / "SB01.cfproject"
    project.save(path)
    reopened = ProductionProject.open(path)
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        prepare_job(reopened, path, None, "文生图", "故事板", "", "", [], ())
    with pytest.raises(ValueError, match="SB01-01 → SB01-02"):
        build_delivery(reopened, path, tmp_path / "交付", tmp_path / "validator.py", tmp_path / "catalog.db")
    assert not (tmp_path / "交付").exists()
    first.fields["动作起止"] = "灯亮后她转身，在同一连续镜头内看向对方。"
    project.shots = [first]
    require_camera_rules(project)


@pytest.mark.parametrize("rules", (ENGLISH, CHINESE))
def test_legacy_review_cannot_bypass_cross_group_gate(tmp_path, rules):
    from src.batch_ai_adapter import prepare_image
    from src.production_export import publish_batch
    from src.production_handoff import confirm_boundary
    from types import SimpleNamespace

    projects = [ProductionProject("门灯", "EP01", group, rules=rules) for group in ("SB01", "SB02")]
    left, right = projects
    paths = []
    for project in projects:
        project.notes = {"本组进入状态": "灯亮", "本组退出状态": "灯亮"}
        project.shots = [Shot(fields={"景别": "中景", "机位/角度": "平视"})]
        project.structure_review = project.fingerprint()
        paths.append(tmp_path / f"{project.group}.cfproject")
        project.save(paths[-1])

    with pytest.raises(ValueError, match="SB01-01 → SB02-01"):
        confirm_boundary(left, right, None, "动作顺接")
    assert not left.handoffs
    workspace = SimpleNamespace(group_paths=lambda episode: paths)
    for project, path in zip(projects, paths):
        with pytest.raises(ValueError, match="SB01-01 → SB02-01"):
            prepare_image(workspace, project, path, {"kind": "board", "episode": "EP01"}, None, {})

    # Older versions allowed this choice to be saved as a reviewed boundary.
    left.handoffs[right.group] = {"left": left.fingerprint(), "right": right.fingerprint(), "review": "动作顺接"}
    with pytest.raises(ValueError, match="SB01-01 → SB02-01"):
        publish_batch(list(zip(projects, paths)), tmp_path / "validator.py", tmp_path / "pair.zip")
    assert not (tmp_path / "pair.zip").exists()


def test_chinese_approved_pair_requires_actual_stable_ids_order_and_reason():
    from src.camera_preflight import boundary_camera_cuts, project_camera_cuts

    left = ProductionProject("门灯", "EP01", "SB01", rules=CHINESE)
    right = ProductionProject("门灯", "EP01", "SB02", rules=CHINESE)
    first, second, third = [Shot(id=sid, fields={"景别": "中景", "机位/角度": angle})
                            for sid, angle in (("L", "正面"), ("R", "斜侧"), ("N", "平视"))]
    left.shots = [first]
    right.shots = [second, third]
    for note in ("允许全组重复", "- 批准镜对：SB02/R → SB01/L | 对称反应", "- 批准镜对：SB01/L → SB02/R | ",
                 "- 批准镜对：SB01/L → SB02/R | 〈具体批准理由〉", "- 批准镜对：SB01-01 → SB02-01 | 对称反应"):
        right.notes["景别衔接核对"] = note
        assert boundary_camera_cuts(left, right)
    right.notes["景别衔接核对"] = "已核对组间状态。\n- 批准镜对：SB01/L → SB02/R | 保留已批准的对称反应镜头"
    assert not boundary_camera_cuts(left, right)
    assert [item.shots for item in project_camera_cuts(right)] == [("SB02-01", "SB02-02")]
    right.shots.reverse()
    assert boundary_camera_cuts(left, right)
    right.shots[0].fields["景别"] = "未定"
    assert not boundary_camera_cuts(left, right)
