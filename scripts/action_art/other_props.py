"""Three-beat illustrations for stage props, eyelines and camera continuity."""

from functools import partial
from math import cos, radians, sin


GOLD = "#bd833a"
GOLD_LIGHT = "#ecc886"
WOOD = "#8b5d3c"
INK = "#354455"
LINE = "#8294a0"
PALE = "#e8eef2"
LIGHT = "#fff1c9"


def sequence(draw):
    return tuple(partial(draw, phase=phase) for phase in range(3))


def floor_mark(c, x, y=204, width=14):
    c.line(((x - width // 2, y), (x + width // 2, y)), GOLD, 3)
    c.line(((x, y - 3), (x, y + 3)), GOLD, 3)


def fan(c, x, y, *, openness=1, size=1):
    """The point at x/y is always the same visible grip."""
    spread = (11, 39, 63)[openness]
    arc = [(-90 + spread * (index / 5 - 1)) for index in range(11)]
    points = [
        (x + cos(radians(angle)) * 24 * size, y + sin(radians(angle)) * 24 * size)
        for angle in arc
    ]
    c.polygon(((x, y), *points), GOLD_LIGHT, outline=GOLD, width=2)
    for index in (0, 2, 4, 6, 8, 10):
        c.line(((x, y), points[index]), GOLD, 1)
    c.ellipse((x - 2, y - 2, x + 2, y + 2), WOOD)


def actor_holding(c, x, y=206, *, grip=(28, -72), color="teal", pose="stand", face=1, scale=1, **kw):
    return c.actor(x, y, pose=pose, color=color, face=face, scale=scale,
                   joints={"hand_front": grip}, **kw)["hand_front"]


def case(c, x, y, size=1):
    """The carried case handle is at x/y, and its base is 26 units lower."""
    c.rect((x - 5 * size, y, x + 5 * size, y + 8 * size), PALE, outline=INK, width=2, radius=2)
    c.rect((x - 16 * size, y + 6 * size, x + 16 * size, y + 26 * size),
           "#ad7944", outline=INK, width=2, radius=3)
    for dx in (-10, 10):
        c.line(((x + dx * size, y + 8 * size), (x + dx * size, y + 24 * size)), GOLD_LIGHT, 2)
    c.rect((x - 4 * size, y + 14 * size, x + 5 * size, y + 19 * size), LIGHT)
    c.line(((x - size, y + 16 * size), (x + 3 * size, y + 16 * size)), GOLD, 1)


def stage_sign(c, x, y):
    c.rect((x - 16, y - 11, x + 16, y + 11), "#dae4e8", outline=INK, width=2, radius=2)
    c.arrow((x - 8, y), (x + 8, y), color=INK, width=2)


def hold_halberd(c, hand, *, angle=-78, size=1, color="gold"):
    # The center of the shaft crosses the unchanged holding point.
    c.prop("halberd", *hand, angle=angle, size=size, color=color)


def reveal_gaze(c, phase):
    c.stage("room")
    # Enlarged framing keeps the small change in the face and fan readable.
    c.actor(259, 215, color="rose", pose="stand", face=-1, scale=.73)
    holder = actor_holding(c, 119, 251, pose="stand", face=1, scale=1.45,
                           grip=(6, -99), look=(0, 0, 1)[phase])
    fan(c, *holder, openness=phase, size=1.05)
    if phase == 2:
        c.arrow((140, 62), (210, 105), color="#99adad", width=1)


def close_fan(c, phase):
    c.stage("room")
    grips = ((5, -101), (18, -88), (18, -57))
    hand = actor_holding(c, 134, 253, color="violet", scale=1.45, grip=grips[phase])
    c.actor(253, 217, color="rose", pose="stand", face=-1, scale=.73)
    fan(c, *hand, openness=(2, 1, 0)[phase], size=1.08)


def follow_staff(c, phase):
    c.stage("studio")
    # Only the camera moves. The staff, person and doorway stay in the same space.
    c.prop("door", 253, 204, size=1.14)
    c.actor(206, 198, color="teal", face=-1, scale=.9)
    c.prop("staff", 87, 137, size=1.57, angle=-73)
    if phase == 0:
        c.camera((28, 28, 168, 133))
    elif phase == 1:
        c.camera((47, 25, 267, 190))


def clear_staff(c, phase):
    c.stage("wall")
    c.line(((247, 28), (247, 201)), LINE, 2)
    stage_sign(c, 243, 96)
    if phase == 0:
        c.actor(108, 205, color="teal", pose="step", face=1)
        c.prop("staff", 231, 133, angle=-77, size=1.35)
    elif phase == 1:
        hand = actor_holding(c, 181, grip=(33, -71), pose="reach")
        c.prop("staff", *hand, angle=-79, size=1.25)
    else:
        hand = actor_holding(c, 108, grip=(25, -73), pose="step", face=-1)
        c.prop("staff", *hand, angle=-73, size=1.22)


def shield_partner(c, phase):
    c.stage("hall")
    c.actor(216, 206, color="rose", pose="stand", face=-1)
    hand = actor_holding(c, 134, grip=((51, -87), (37, -80), (21, -73))[phase], scale=1.12)
    c.prop("shield", hand[0] + 16, hand[1] - 18, size=(1.70, 1.55, 1.46)[phase], angle=(0, -8, -12)[phase])


def shield_sign(c, phase):
    c.stage("wall")
    stage_sign(c, 226, 105)
    floor_mark(c, 265)
    if phase == 0:
        hand = actor_holding(c, 165, grip=(38, -82), pose="reach")
        c.prop("shield", hand[0] + 20, hand[1] - 9, size=1.45)
    elif phase == 1:
        hand = actor_holding(c, 204, grip=(34, -43), pose="bend")
        c.prop("shield", hand[0] + 17, hand[1], size=1.45, angle=8)
    else:
        c.actor(157, 205, color="teal", face=1, pose="look-back")
        c.prop("shield", 265, 167, size=1.43, angle=8)


def halberd_shadow(c, phase):
    c.stage("door", light="backlit")
    c.rect((161, 26, 275, 205), "#b6a08d", outline=LINE, width=3)
    c.line(((218, 28), (218, 202)), "#9a837a", 2)
    if not phase:
        c.beam((17, 185), (204, 94), width=32, color="sun")
    shadow_position = ((213, 126), (222, 126), (234, 126))[phase]
    c.prop("halberd", *shadow_position, size=1.26, angle=-72, color="#55465a")
    if phase:
        hand = actor_holding(c, (0, 76, 119)[phase], grip=(23, -75),
                             pose=("stand", "step", "stand")[phase], color="slate")
        hold_halberd(c, hand, angle=-72, size=1.05)


def head_in_frame(c, phase):
    c.stage("hall")
    floor_mark(c, 125)
    hand = actor_holding(c, 125, 206, grip=((32, -53), (38, -92), (38, -92))[phase],
                         color="blue", scale=.94, pose=("stand", "raise", "raise")[phase])
    hold_halberd(c, hand, angle=(-57, -82, -82)[phase], size=1.07)
    if phase == 2:
        c.camera((59, 7, 239, 142))


def past_step(c, phase):
    c.stage("studio")
    # Three rock-solid floor heights show the planted support foot at each beat.
    c.polygon(((0, 205), (123, 205), (123, 188), (209, 188), (209, 171), (320, 171),
               (320, 240), (0, 240)), "#c9d0d4", outline=LINE)
    for y, x in ((205, 123), (188, 209), (171, 320)):
        c.line(((x - 55, y), (x, y)), "#7e8f9b", 2)
    x, y = ((69, 205), (159, 188), (231, 171))[phase]
    hand = actor_holding(c, x, y, grip=(27, -68), pose=("step", "step", "stand")[phase],
                         color="teal", scale=.86)
    hold_halberd(c, hand, angle=-53, size=1.05)


def ornament_settles(c, phase):
    c.stage("studio")
    actor_holding(c, 111, 210, color="violet", grip=(43, -85), scale=.95)
    # Shaft and body remain fixed, with motion carried by the hanging bead alone.
    c.prop("halberd", 152, 129, angle=-90, size=1.30)
    anchor = (157, 65)
    bead = ((185, 91), (165, 104), (157, 105))[phase]
    c.line((anchor, bead), WOOD, 2)
    c.ellipse((bead[0] - 5, bead[1] - 5, bead[0] + 5, bead[1] + 5),
              GOLD_LIGHT, outline=GOLD, width=2)
    if phase < 2:
        c.line(((bead[0] + 6, bead[1] + 5), (bead[0] + 15, bead[1] + 2)), "#b6ac94", 2)


def halberd_handoff(c, phase):
    c.stage("hall")
    floor_mark(c, 158)
    left_grips = ((33, -75), (45, -75), (13, -48))
    right_grips = ((11, -49), (46, -72), (33, -72))
    giving = actor_holding(c, 111, grip=left_grips[phase], pose=("reach", "reach", "stand")[phase])
    receiving = actor_holding(c, 203, grip=right_grips[phase], pose=("stand", "reach", "reach")[phase],
                              color="rose", face=-1)
    hand = giving if phase < 2 else receiving
    angle = -83 if phase != 1 else -90
    hold_halberd(c, hand, angle=angle, size=1.1)
    if phase == 1:
        c.ellipse((giving[0] - 4, giving[1] - 3, giving[0] + 3, giving[1] + 3), "#76b5ac")
        c.ellipse((receiving[0] - 3, receiving[1] - 3, receiving[0] + 4, receiving[1] + 3), "#db9d91")


def halberd_fog(c, phase):
    c.stage("night", light="dim")
    c.glow(266, 62, 24, color="sun")
    c.beam((266, 63), (151, 137), width=37, color="sun")
    x = (91, 160, 233)[phase]
    hand = actor_holding(c, x, 210, color="blue", grip=(25, -75), pose=("step", "step", "stand")[phase])
    hold_halberd(c, hand, angle=-75, size=1.05)
    mist = ((-35, 129, 183, 170), (-16, 134, 194, 176), (-40, 151, 200, 205), (16, 159, 186, 204))
    for ellipse in mist:
        c.ellipse(ellipse, (188, 206, 220, 32))


def stage_rack(c, center=201, height=161):
    c.line(((center - 29, height + 43), (center - 29, height),
            (center + 28, height), (center + 28, height + 43)), LINE, 4)
    c.line(((center - 40, height + 43), (center + 42, height + 43)), INK, 3)
    c.rect((center + 6, height + 11, center + 25, height + 22), LIGHT,
           outline="#bca884", width=1, radius=2)
    for dx in (-1, 3, 7):
        c.line(((center + 13 + dx, height + 14), (center + 13 + dx, height + 19)), WOOD, 1)


def screen_prop(c, x, y, *, angle=0, size=1):
    """Draw the stylized, clearly marked prop as a single blunt silhouette."""
    origin = ((-19, -8), (20, -8), (20, 1), (5, 1), (1, 14), (-9, 14), (-9, 1), (-19, 1))

    def point(dx, dy):
        rot = radians(angle)
        return (x + size * (dx * cos(rot) - dy * sin(rot)), y + size * (dx * sin(rot) + dy * cos(rot)))

    c.polygon(tuple(point(*offset) for offset in origin), "#728399", outline=INK, width=2)
    c.polygon(tuple(point(*v) for v in ((15, -8), (20, -8), (20, 1), (15, 1))), "#edb16b")


def leave_prop(c, phase):
    c.stage("room")
    stage_rack(c)
    if phase == 0:
        hand = actor_holding(c, 116, grip=(35, -62), pose="reach", color="slate")
        screen_prop(c, hand[0] + 10, hand[1], angle=20)
    elif phase == 1:
        actor_holding(c, 141, grip=(53, -47), pose="reach", color="slate")
        screen_prop(c, 201, 159)
    else:
        c.actor(104, 206, pose="step", face=-1, color="slate")
        screen_prop(c, 201, 159)
        c.camera((124, 98, 276, 212))


def pass_door_with_prop(c, phase):
    c.stage("studio")
    c.rect((129, 74, 189, 205), "#7d8277", outline=LINE, width=3)
    c.rect((137, 82, 180, 204), "#abb6b1")
    c.polygon(((137, 82), (158, 99), (158, 208), (137, 204)), "#c6aa7b", outline="#6a6556", width=2)
    x = (78, 150, 231)[phase]
    hand = actor_holding(c, x, grip=(17, -48), pose="step", color="slate", scale=.95)
    screen_prop(c, hand[0] + 7, hand[1] + 4, angle=65, size=.77)
    c.line(((23, 209), (294, 209)), "#9bacb5", 1)


def radio_before_speaking(c, phase):
    c.stage("hall")
    grip = ((18, -64), (16, -91), (16, -91))[phase]
    hand = actor_holding(c, 112, 246, grip=grip, color="teal", scale=1.38,
                         pose="stand", look=(0, 1, 1)[phase])
    c.prop("radio", hand[0] + 2, hand[1] - 5, size=1.06)
    if phase == 2:
        for dx in (0, 8, 16):
            c.line(((157 + dx, 77 + dx * .24), (162 + dx, 73 + dx * .24)), "#8ca1a9", 2)


def set_down_case(c, phase):
    c.stage("studio")
    floor_mark(c, 228, width=40)
    if phase == 0:
        hand = actor_holding(c, 120, grip=(22, -59), color="blue", pose="step")
        case(c, *hand)
    elif phase == 1:
        hand = actor_holding(c, 199, grip=(29, -28), color="blue", pose="crouch")
        case(c, *hand)
    else:
        c.actor(195, 206, color="blue", pose="half-rise", face=1,
                joints={"hand_front": (24, -52)})
        case(c, 228, 178)


def phone_lights_gaze(c, phase):
    c.stage("room", light="dim")
    c.actor(246, 209, color="rose", pose="stand", face=-1, scale=.94)
    x, y, s = 111, 209, 1.02
    hand = (x + 31 * s, y - 90 * s)
    if phase:
        c.glow(hand[0] + 4, hand[1] - 6, 23, color="sun")
    joints = {"hand_front": (31, -90)}
    if phase == 1:
        joints.update(head=(11, -116), neck=(6, -110))
    c.actor(x, y, pose=("reach", "reach", "stand")[phase], color="violet", scale=s,
            joints=joints, look=(0, 1, 1)[phase])
    c.rect((hand[0] - 4, hand[1] - 15, hand[0] + 12, hand[1] + 7), INK, radius=3)
    c.rect((hand[0] - 2, hand[1] - 12, hand[0] + 10, hand[1] + 4),
           (("#627283", LIGHT, LIGHT)[phase]), radius=1)
    if phase == 2:
        c.arrow((129, 70), (218, 78), color="#9c9fac", width=1)


SCENES = {
    "halberds-01": sequence(halberd_shadow),
    "halberds-02": sequence(head_in_frame),
    "halberds-03": sequence(past_step),
    "halberds-04": sequence(ornament_settles),
    "halberds-05": sequence(halberd_handoff),
    "halberds-06": sequence(halberd_fog),
    "stage-01": sequence(reveal_gaze),
    "stage-02": sequence(close_fan),
    "stage-03": sequence(follow_staff),
    "stage-04": sequence(clear_staff),
    "stage-05": sequence(shield_partner),
    "stage-06": sequence(shield_sign),
    "modern-01": sequence(leave_prop),
    "modern-02": sequence(pass_door_with_prop),
    "modern-03": sequence(radio_before_speaking),
    "modern-04": sequence(set_down_case),
    "modern-05": sequence(phone_lights_gaze),
}
