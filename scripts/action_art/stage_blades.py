"""Three-beat stage blocking, prop continuity and camera examples."""

from functools import partial
from PIL import ImageFilter


AMBER = "#f4bd67"
TAPE = "#e9b879"
TEAL_LIGHT = "#6fcdd2"
SWORD_ECHO = (111, 205, 210, 109)


def panels(draw):
    return tuple(partial(draw, beat=beat) for beat in range(3))


def tape(c, x, y):
    c.line(((x - 8, y + 2), (x + 8, y - 2)), TAPE, width=2)
    c.line(((x - 3, y - 3), (x + 3, y + 3)), TAPE, width=2)


def soften(c, radius):
    c.image.paste(c.image.filter(ImageFilter.GaussianBlur(radius * c.scale)))


def counter(c, x=129, y=153, w=156, depth=8):
    c.polygon(((x, y), (x + w, y), (x + w - 12, y + depth), (x - 12, y + depth)),
              "#526371", "#83949b", width=2)
    c.rect((x - 12, y + depth, x + w - 13, y + depth + 8), "#334452")
    c.line(((x + 8, y + depth + 7), (x + 5, 205)), "#4a5d6b", width=6)
    c.line(((x + w - 24, y + depth + 7), (x + w - 20, 205)), "#4a5d6b", width=6)


def holder(c, x, foot_y, grip, *, pose="stand", face=1, scale=1.0, color="teal", look=None, stride=1):
    """Pose a visible hand at an unchanged stage-prop contact point."""
    dx = (grip[0] - x) / (face * scale)
    dy = (grip[1] - foot_y) / scale
    joints = {"hand_front": (dx, dy), "elbow_front": ((dx + 10) * 0.5, (dy - 88) * 0.5 + 5)}
    if pose == "step" and stride < 0:
        joints.update(foot_front=(-23, -3), foot_back=(31, -2), knee_front=(-11, -27), knee_back=(16, -34))
    return c.actor(x, foot_y, color=color, pose=pose, face=face, scale=scale, joints=joints, look=look)


def saber_light(c, *, beat):
    c.stage("night", "dim")
    c.rect((51, 21, 67, 32), "#415465", radius=3)
    c.beam((63, 31), ((182, 99), (212, 126), (178, 82))[beat],
           width=(25, 32, 34)[beat], color="sun")
    hand = (173, 132)
    c.prop("saber", *hand, angle=12, size=0.92, color="#6e6d63" if beat == 0 else "gold")
    holder(c, 153, 208, hand, pose="stand", look=(225, 97))
    if beat == 1:
        c.glow(219, 141, 21, color="sun")
        c.line(((193, 137), (231, 144)), "#f9da97", width=3)
    if beat == 2:
        c.glow(158, 83, 27, color="sun")
        c.camera((71, 36, 295, 204))


def saber_table(c, *, beat):
    c.stage("room")
    c.actor(237, 188, color="rose", face=-1, scale=0.78, look=(133, 102))
    counter(c, x=125, y=152, w=154)
    tape(c, 150, 154)
    hand = ((146, 127), (150, 152), (126, 116))[beat]
    prop = (150, 151) if beat == 2 else hand
    c.prop("saber", *prop, angle=0, size=0.84)
    holder(c, (112, 113, 109)[beat], 208, hand,
           pose=("reach", "bend", "stand")[beat], look=((159, 145), (153, 152), (236, 91))[beat])


def saber_shadow(c, *, beat):
    c.stage("wall", "dim")
    c.beam((18, 56), (274, 162), width=150, color="sun")
    c.rect((8, 45, 28, 70), "#7a7880", outline="#bcad9d", radius=4)
    c.rect((21, 49, 26, 67), "#ead1a4", radius=1)
    c.line(((18, 70), (18, 204)), "#56616c", width=5)
    frame = ((231, 202, 1.04), (219, 202, 1.04), (219, 202, 1.04))[beat]
    shadow = c.actor(frame[0], frame[1], scale=frame[2], color="slate", silhouette=True,
                     pose="stand", look=(210, 137))
    c.prop("saber", *shadow["hand_front"], angle=24, size=0.85, color="#213039")
    if beat:
        c.prop("saber", 144, 146, angle=24, size=0.85)
        holder(c, 124, 205, (144, 146), pose="step" if beat == 1 else "stand", look=(228, 122))
    if beat == 2:
        c.camera((34, 23, 318, 236))


def saber_focus(c, *, beat):
    c.stage("room", "dim")
    c.rect((39, 24, 76, 169), "#394857", outline="#647b84")
    c.line(((50, 27), (50, 166)), "#506875", width=3)
    caller = c.actor(82, 188, face=1, color="rose", scale=0.82,
                     pose="reach" if beat == 1 else "stand", look=(210, 58))
    grip = (151, 140)
    if beat == 2:
        soften(c, 1.7)
    holder(c, 212, 222, grip, face=-1, scale=1.25,
           pose="stand", look=caller["head"])
    if beat == 0:
        soften(c, 2.1)
        c.glow(100, 128, 26, color="sun")
    c.prop("saber", *grip, angle=-169, size=1.23, color="gold" if beat == 0 else "#ad9572")
    c.ellipse((grip[0] - 4, grip[1] - 6, grip[0] + 7, grip[1] + 6), "skin", outline="ink")
    if beat == 1:
        sx, sy = caller["head"]
        c.line(((sx + 14, sy - 2), (sx + 24, sy - 6)), TAPE, width=2)
        c.line(((sx + 17, sy + 5), (sx + 27, sy + 5)), TAPE, width=2)
    elif beat == 2:
        c.camera((101, 45, 305, 198))


def saber_exit(c, *, beat):
    c.stage("night", "dim")
    c.beam((170, 9), (174, 200), width=105, color="sun")
    c.ellipse((114, 181, 241, 222), "#38454a")
    counter(c, x=124, y=145, w=100)
    tape(c, 154, 146)
    grip = (153, 143)
    c.prop("saber", *grip, angle=0, size=0.83)
    if beat == 0:
        holder(c, 110, 207, grip, pose="bend", look=(168, 142))
    else:
        c.actor((0, 86, 29)[beat], (0, 211, 212)[beat], face=-1,
                pose="look-back" if beat == 1 else "step", color="teal",
                look=(155, 141) if beat == 1 else None)
    c.glow(183, 143, 25, color="sun")


def saber_transition(c, *, beat):
    c.stage("hall" if beat < 2 else "door", "backlit")
    grip = ((133, 151), (151, 148), (161, 147))[beat]
    c.prop("saber", *grip, angle=17, size=0.83)
    holder(c, (111, 125, 138)[beat], 208, grip, pose="look-back" if beat == 0 else "step",
           look=(203, 80), stride=-1 if beat == 1 else 1)
    if beat == 1:
        c.polygon(((-18, 169), (59, 161), (199, 103), (338, 76), (339, 156), (166, 188), (-10, 216)),
                  "#28596d")
        c.polygon(((-15, 173), (59, 163), (194, 114), (339, 86), (337, 144), (164, 172), (-8, 207)),
                  "#4e8797")
        c.line(((-8, 190), (84, 172), (196, 136), (335, 104)), "#b0eff2", width=6)
    elif beat == 2:
        c.glow(251, 96, 60, color=TEAL_LIGHT)
        c.line(((228, 140), (319, 111)), TEAL_LIGHT, width=5)


def spear_corner(c, *, beat):
    c.stage("hall")
    x = (83, 138, 218)[beat]
    grip = (x + 24, 141)
    c.prop("spear", *grip, angle=-5, size=0.84)
    holder(c, x, 207, grip, pose="step", look=(254, 130), stride=-1 if beat == 1 else 1)
    c.rect((0, 25, 160, 212), "#314554", outline="#627983", width=2)
    c.rect((148, 27, 160, 211), "#455d69")
    c.line(((159, 25), (159, 212)), "#8ba3a8", width=3)
    c.line(((159, 212), (232, 216)), "#596e76", width=2)


def spear_wall(c, *, beat):
    c.stage("wall")
    c.line(((238, 31), (238, 206)), "#859a9b", width=3)
    c.rect((238, 32, 313, 202), "#3e515d")
    c.ellipse((189, 196, 211, 205), "#343e49", outline=TAPE, width=2)
    grip = ((150, 141), (219, 145), (219, 145))[beat]
    c.prop("spear", *grip, angle=(-64, -68, -68)[beat], size=1.05)
    if beat < 2:
        holder(c, (126, 184)[beat], 205, grip, pose="step" if beat == 0 else "reach", look=(237, 85))
    else:
        c.actor(180, 205, pose="stand", look=(238, 86))


def spear_door(c, *, beat):
    c.stage("door")
    c.rect((192, 49, 245, 206), "#24363c", outline="#627b7d", width=5)
    c.line(((190, 201), (245, 201)), TAPE, width=3)
    x = (112, 173, 274)[beat]
    grip = (x + (22, 19, 5)[beat], (138, 122, 127)[beat])
    c.prop("spear", *grip, angle=(-10, -54, -54)[beat], size=(0.95, 1.0, 1.0)[beat])
    holder(c, x, 208, grip, pose="stand" if beat == 0 else "step", look=(278, 97), stride=-1 if beat == 1 else 1)


def spear_marker(c, *, beat):
    c.stage("night")
    c.line(((48, 184), (316, 184)), "#4c606c", width=4)
    c.ellipse((174, 183, 192, 193), "#34484e", outline=AMBER, width=2)
    c.glow(271, 63, 22, color="sun")
    c.ellipse((268, 60, 275, 67), "#fbd6a2")
    grip = ((185, 125), (183, 128), (183, 128))[beat]
    c.prop("spear", *grip, angle=-90, size=1.04)
    holder(c, 144, 208, grip, pose="stand", look=((181, 189), (267, 64), (267, 64))[beat])
    if beat == 2:
        c.camera((60, 48, 284, 216))


def spear_parallel(c, *, beat):
    c.stage("hall")
    c.line(((10, 175), (312, 175)), "#768587", width=2)
    c.line(((10, 211), (312, 211)), "#768587", width=2)
    offset = (0, 22, 42)[beat]
    c.actor(139 + offset, 173, pose="step", color="rose", scale=0.68, look=(282, 128),
            joints={"foot_front": (18 if beat % 2 == 0 else -13, 0),
                    "foot_back": (-17 if beat % 2 == 0 else 13, 0)})
    grip = (78 + offset, 153)
    c.prop("spear", *grip, angle=-9, size=0.91)
    holder(c, 62 + offset, 210, grip, pose="step", look=(269, 143), stride=-1 if beat == 1 else 1)


def spear_banners(c, *, beat):
    c.stage("hall", "backlit")
    flutter = (16, 23, 23)[beat]
    for x, color in ((52, "#7b5a56"), (159, "#916e55"), (258, "#6d5b68")):
        c.line(((x, 38), (x, 193)), "#60767d", width=3)
        c.polygon(((x, 47), (x+flutter, 50), (x+flutter+17, 41), (x+flutter+14, 62), (x, 68)), color)
    x = (108, 138, 138)[beat]
    grip = (x + 28, 129)
    c.prop("spear", *grip, angle=-78, size=0.9)
    tip = (grip[0]+9, grip[1]-43)
    c.line((tip, (tip[0]+12, tip[1]+4), (tip[0]+flutter+13, tip[1]-2)), "#d27b63", width=4)
    c.line((tip, (tip[0]+14, tip[1]+9), (tip[0]+flutter+6, tip[1]+5)), "#bd7365", width=3)
    c.polygon(((x-11, 136), (x+12, 136), (x+flutter+5, 164), (x-8, 169)), "#508e89")
    holder(c, x, 209, grip, pose="step", look=(280, 92), stride=-1 if beat else 1)
    if beat == 2:
        c.camera((86, 37, 286, 187))


def sword_fade(c, *, beat):
    c.stage("night", "dim")
    grip = (149, 140)
    if beat < 2:
        c.glow(194 if beat == 0 else 154, 139, (62, 26)[beat], color=TEAL_LIGHT)
    c.prop("sword", *grip, angle=-5, size=1.0, color="gold" if beat == 0 else "#ac9980")
    holder(c, 118, 208, grip, look=(206, 132))
    if beat < 2:
        c.line((((171 if beat == 0 else 144), 136), ((218 if beat == 0 else 169), 133)),
               "#aef1ee", width=4 if beat == 0 else 2)
    if beat != 0:
        c.camera((72, 57, 256, 195))


def sword_reflection(c, *, beat):
    c.stage("night", "dim")
    if beat:
        c.beam((318, 53), (193, 134), width=33, color="sun")
        c.glow(299, 58, 33, color="sun")
    grip = (158, 131)
    c.prop("sword", *grip, angle=11, size=1.05)
    holder(c, 125, 207, grip, look=(230, 130) if beat < 2 else (302, 48))
    if beat:
        c.line(((202, 138), (228, 143)), "#ffe8b7", width=4)
    if beat == 2:
        c.camera((73, 27, 313, 207))


def sword_guard(c, *, beat):
    c.stage("room")
    c.rect((243, 29, 288, 205), "#485b67", outline="#788a8e")
    grip = (168, 130)
    c.prop("sword", *grip, angle=17, size=1.06)
    figure = holder(c, 130, 207, grip, look=(216, 129))
    ex, ey = figure["elbow_front"]
    c.line(((ex + 11, ey + 4), (ex + 14, ey - 3)), "#569c9d", width=3)
    if beat:
        frame = (86, 60, 290, 213) if beat == 1 else (128, 104, 268, 209)
        c.camera(frame)


def sword_stand(c, *, beat):
    c.stage("studio")
    c.rect((150, 189, 268, 197), "#415561", outline="#799093", width=2, radius=2)
    for x in (181, 213):
        c.line(((x-6, 129), (x, 144), (x, 187)), "#6a8290", width=5)
        c.line(((x+6, 129), (x, 144)), "#6a8290", width=5)
    tape(c, 207, 191)
    grip = ((143, 123), (163, 135), (163, 135))[beat]
    c.prop("sword", *grip, angle=0, size=1.06)
    if beat < 2:
        holder(c, (110, 126)[beat], 207, grip, pose="step" if beat == 0 else "reach", look=(229, 131))
    else:
        c.actor(72, 209, face=-1, pose="step", look=(36, 90))


def sword_scabbard(c, *, beat):
    c.stage("door", "normal")
    x = (128, 171, 197)[beat]
    foot_y, scale = (206, 203, 186)[beat], (1.0, 0.95, 0.81)[beat]
    c.polygon(((x-16, foot_y-84*scale), (x+13, foot_y-81*scale),
               (x-25, foot_y-35*scale), (x-40, foot_y-43*scale)), "#538e89")
    pose = ("look-back", "step", "step")[beat]
    figure = c.actor(x, foot_y, pose=pose, scale=scale, look=(x-63, foot_y-135*scale) if beat == 0 else (x+26, foot_y-155*scale))
    hip_x, hip_y = figure["hip"]
    collar = (hip_x-11, hip_y-3)
    c.line((collar, (hip_x-34*scale, hip_y+48*scale)), "#334052", width=9)
    c.line((collar, (hip_x-34*scale, hip_y+48*scale)), "#b4956d", width=4)
    c.line(((collar[0]-3, collar[1]+6), (collar[0]+4, collar[1]-1)), AMBER, width=3)
    if beat == 2:
        hx, hy = figure["head"]
        c.ellipse((hx-8*scale, hy-11*scale, hx+11*scale, hy+9*scale), "#426866", outline="ink")
        c.camera((77, 19, 317, 199))


def sword_echo(c, *, beat):
    c.stage("door", "backlit")
    x = (93, 134, 185)[beat]
    grip = (x + 25, 138)
    if beat == 0:
        for dx, dy, angle in ((44, -62, -40), (75, -35, -19), (104, -4, -8)):
            c.prop("sword", grip[0]+dx, grip[1]+dy, angle=angle, size=0.74, color=SWORD_ECHO)
    if beat == 1:
        for dx, dy, angle in ((11, -27, -13), (9, -11, -6), (0, 0, 4)):
            c.prop("sword", grip[0]+dx, grip[1]+dy, angle=angle, size=0.85, color=SWORD_ECHO)
    if beat == 2:
        c.glow(234, 144, 38, color=TEAL_LIGHT)
        c.prop("sword", *grip, angle=4, size=0.85)
    holder(c, x, 209, grip, pose="step", look=(263, 113), stride=-1 if beat == 1 else 1)


SCENES = {
    "sabers-01": panels(saber_light),
    "sabers-02": panels(saber_table),
    "sabers-03": panels(saber_shadow),
    "sabers-04": panels(saber_focus),
    "sabers-05": panels(saber_exit),
    "sabers-06": panels(saber_transition),
    "spears-01": panels(spear_corner),
    "spears-02": panels(spear_wall),
    "spears-03": panels(spear_door),
    "spears-04": panels(spear_marker),
    "spears-05": panels(spear_parallel),
    "spears-06": panels(spear_banners),
    "swords-01": panels(sword_fade),
    "swords-02": panels(sword_reflection),
    "swords-03": panels(sword_guard),
    "swords-04": panels(sword_stand),
    "swords-05": panels(sword_scabbard),
    "swords-06": panels(sword_echo),
}
