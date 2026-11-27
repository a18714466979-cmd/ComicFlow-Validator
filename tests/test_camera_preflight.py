from src.camera_preflight import CameraCut, camera_cuts
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

    assert "禁止连续三镜同景别且同角度" in instructions_for(SHOT_TASK, ENGLISH)
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
