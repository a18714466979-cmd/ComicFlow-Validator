"""Acting, partner blocking, and screen-direction studies for the preset library."""

from functools import partial


def beats(draw):
    return tuple(partial(draw, beat=index) for index in range(3))


def reach(c, x, y, hand, *, color="teal", face=1, pose="reach", look=None, scale=1, back=None, head=None):
    """Anchor a visible hand at the contact point in stage coordinates."""
    dx, dy = (hand[0] - x) / scale * face, (hand[1] - y) / scale
    joints = {"hand_front": (dx, dy), "elbow_front": (dx * .52, (dy - 89) * .5 + 9)}
    if back:
        bx, by = (back[0] - x) / scale * face, (back[1] - y) / scale
        joints.update(hand_back=(bx, by), elbow_back=(bx * .61, (by - 87) * .5 + 12))
    if head:
        joints["head"] = head
    return c.actor(x, y, pose=pose, color=color, face=face, scale=scale, joints=joints, look=look)


def window(c, box=(230, 40, 288, 110), *, lit=True):
    left, top, right, bottom = box
    glass = "#938457" if lit else "#314658"
    c.rect(box, glass, "#acb1ad", 2)
    c.line([(left, (top + bottom) * .5), (right, (top + bottom) * .5)], "#acb1ad", 2)
    c.line([((left + right) * .5, top), ((left + right) * .5, bottom)], "#acb1ad", 2)
    c.rect((left - 5, bottom, right + 5, bottom + 4), "#788b91")


def table(c, left, top, right, floor=199):
    c.rect((left + 8, top + 8, left + 14, floor), "#685b58")
    c.rect((right - 13, top + 8, right - 7, floor), "#685b58")
    c.rect((left, top, right, top + 9), "#82736a", "#a28f7c", 1, 2)


def doorway(c, left, right, *, floor=197, frame="#87969a", interior="#172a39"):
    c.rect((left, 49, right, floor), interior)
    c.line([(left, floor), (left, 49), (right, 49), (right, floor)], frame, 6)
    c.line([(left - 3, floor), (right + 3, floor)], "#a6a18d", 3)


def column(c, left, right, *, base=207):
    c.rect((left, 31, right, base), "#657b8d", "#879da6", 2)
    c.rect((left + 1, 32, left + 7, base), "#899da3")
    c.rect((right - 8, 32, right, base), "#52667b")
    c.rect((left - 4, base - 11, right + 4, base), "#65768a", "#9aaaaf", 1)


def performance_02(c, beat):
    c.stage("room")
    table(c, 176, 137, 272)
    c.rect((209, 128, 233, 137), "#e4b762", "#fbce82", 1, 2)
    if beat:
        c.glow(224, 132, 13)
    # The chair stays put and the supporting hand stays on its near edge.
    c.line([(94, 135), (94, 171), (132, 171), (132, 200)], "#879ba1", 5)
    c.line([(94, 169), (94, 199)], "#6e858d", 5)
    x = (109, 118, 118)[beat]
    y = (207, 203, 203)[beat]
    pose = ("sit", "half-rise", "half-rise")[beat]
    arm = (132, 167)
    reach(c, x, y, arm, pose=pose, look=(224, 132) if beat == 2 else (152, 155),
          color="teal", back=(97, 165) if beat < 2 else (108, 152),
          head=(17, -115) if beat == 2 else None)
    if beat == 1:
        c.arrow((77, 160), (77, 131))


def performance_03(c, beat):
    c.stage("room")
    giver_x, receiver_x = 108, 215
    object_x = (147, 161, 189)[beat]
    object_y = (137, 135, 138)[beat]
    giver_hand = ((139, 141), (151, 136), (126, 154))[beat]
    receiving_hand = ((190, 155), (171, 137), (198, 141))[beat]
    reach(c, giver_x, 205, giver_hand, color="teal", look=(object_x, object_y))
    reach(c, receiver_x, 205, receiving_hand, face=-1, color="rose", look=(object_x, object_y))
    # A single envelope travels continuously. Fingers at both edges mark the actual handoff.
    c.prop("parcel", object_x, object_y, size=.84)
    if beat in (0, 1):
        c.ellipse((giver_hand[0] - 3, giver_hand[1] - 2, giver_hand[0] + 3, giver_hand[1] + 3),
                  "#85d3c9")
    if beat >= 1:
        c.ellipse((receiving_hand[0] - 3, receiving_hand[1] - 2,
                   receiving_hand[0] + 3, receiving_hand[1] + 3), "#f2aaa4")
    if beat == 0:
        c.arrow((142, 168), (166, 168))


def partners_02(c, beat):
    c.stage("room")
    if beat == 0:
        c.actor(101, 203, pose="step", look=(203, 146))
        c.actor(207, 205, pose="crouch", color="rose", face=-1, look=(103, 97))
        c.arrow((106, 178), (126, 178))
    elif beat == 1:
        reach(c, 127, 206, (168, 143), pose="bend", look=(196, 139))
        reach(c, 202, 205, (169, 145), color="rose", face=-1, pose="half-rise",
              look=(133, 108), back=(222, 169))
    else:
        reach(c, 133, 205, (165, 131), look=(198, 95))
        reach(c, 192, 205, (166, 131), color="rose", face=-1, pose="stand", look=(133, 95))


def paths_01(c, beat):
    c.stage("hall", light="dim")
    c.polygon([(227, 35), (260, 41), (299, 210), (159, 210)], "#403e38")
    c.ellipse((174, 195, 295, 218), "#776848")
    x = (123, 151, 224)[beat]
    c.actor(x, 206, pose=("step", "step", "stand")[beat], silhouette=beat < 2, look=(253, 148))
    column(c, 86, 142)
    if beat == 1:
        c.arrow((161, 222), (202, 222), color="#b7c4ca")
    if beat == 2:
        c.ellipse((210, 204, 238, 211), None, "#e5c37c", 2)


def performance_01(c, beat):
    c.stage()
    doorway(c, 112, 187)
    window(c)
    c.polygon([(230, 107), (286, 107), (307, 205), (207, 205)], "#524e40")
    c.line([(115, 198), (197, 198)], "#cbb795", 3)
    edge = (178, 151, 151)[beat]
    c.polygon([(114, 53), (edge, 62), (edge, 188), (114, 196)], "#536675", "#a0aeb4", 2)
    handle = (edge - 9, 131)
    c.ellipse((handle[0] - 4, 127, handle[0] + 4, 135), "#e4b35c")
    reach(c, (203, 182, 182)[beat], 205, handle, face=-1,
          pose=("step", "stand", "stand")[beat], look=((132, 108), (52, 105), (258, 76))[beat])
    if beat == 0:
        c.arrow((200, 213), (171, 213))
    if beat == 2:
        c.glow(259, 71, 19)


def performance_04(c, beat):
    c.stage("hall", light="dim")
    c.polygon([(246, 38), (311, 22), (311, 192), (246, 160)], "#354958", "#647886", 2)
    c.line([(269, 33), (269, 174)], "#7a8993", 2)
    x = (100, 178, 178)[beat]
    c.actor(x, 204, pose=("step", "stand", "stand")[beat],
            face=1, look=((225, 164), (232, 127), (303, 82))[beat],
            joints={"head": (10, -124), "neck": (5, -111)} if beat == 2 else None)
    if beat == 0:
        c.arrow((99, 216), (142, 216))
    if beat == 2:
        for offset in (0, 10, 20):
            c.line([(293 + offset, 82), (286 + offset, 92), (293 + offset, 102)],
                   "#e7c880", 2)


def performance_05(c, beat):
    c.stage()
    window(c, (237, 38, 284, 100), lit=False)
    c.actor(228, 202, scale=.92, pose="sit", color="rose", face=-1, look=(96, 105))
    table(c, 101, 151, 218)
    y = (132, 143.3, 143.3)[beat]
    hand = ((145, 136), (145, 145), (118, 140))[beat]
    actor = reach(c, 92, 204, hand, pose="sit", scale=.94, look=((148, 143), (148, 143), (222, 110))[beat])
    c.prop("glass", 151, y, size=.77)
    if beat == 0:
        c.arrow((172, 120), (172, 142))
    if beat == 2:
        head_x, head_y = actor["head"]
        c.ellipse((head_x + 8, head_y + 5, head_x + 11, head_y + 9), "#132330")
        c.line([(head_x + 19, head_y + 7), (head_x + 25, head_y + 7)], "#f4ce91", 2)


def performance_06(c, beat):
    c.stage("hall")
    doorway(c, 234, 290, interior="#665e45")
    c.polygon([(236, 195), (288, 195), (307, 222), (199, 222)], "#6f6049")
    # The exit is always frame-right. The held eye line breaks a beat before the step.
    c.actor((144, 146, 187)[beat], 204, pose=("look-back", "stand", "step")[beat],
            look=((32, 102), (98, 108), (262, 111))[beat], face=1)
    if beat == 2:
        c.arrow((184, 217), (223, 217))
    else:
        c.line([(128, 204), (159, 203)], "#d8ad70", 2)


def partners_01(c, beat):
    c.stage("wall")
    reach(c, 112, 205, (159, 146), look=(207, 105))
    reply = ((197, 164), (185, 152), (160, 146))[beat]
    reach(c, 207, 205, reply, color="rose", face=-1,
          look=((159, 146), (111, 96), (115, 97))[beat], pose="stand")
    if beat == 0:
        c.arrow((177, 128), (164, 141))
    if beat == 2:
        c.ellipse((155, 141, 166, 152), "#a9d4c8", "#e1bb92", 1)


def partners_03(c, beat):
    c.stage()
    doorway(c, 145, 220, interior="#5a5548")
    c.polygon([(151, 192), (216, 192), (273, 223), (112, 223)], "#5f5a4d")
    c.actor(227, 201, pose="stand", face=-1, look=((120, 94), (178, 117), (254, 113))[beat])
    follower_x = (96, 173, 262)[beat]
    c.actor(follower_x, 207, color="rose", scale=.9, pose=("step", "step", "stand")[beat],
            look=(263, 145))
    if beat < 2:
        c.arrow((follower_x + 7, 220), (follower_x + 37, 220))
    else:
        c.line([(220, 211), (277, 211)], "#e7c786", 3)


def partners_04(c, beat):
    c.stage("hall")
    c.rect((223, 29, 311, 116), "#536776", "#8aa0a7", 2)
    c.polygon([(220, 113), (311, 113), (294, 131), (218, 131)], "#4c5c68")
    center = (139, 156, 184)[beat]
    height = (144, 141, 140)[beat]
    reach(c, center - 58, 204, (center - 26, height + 12), pose=("step", "stand", "step")[beat],
          look=(250, 130))
    reach(c, center + 59, 204, (center + 26, height + 12), face=-1,
          pose=("step", "stand", "step")[beat], color="rose", look=(center, height))
    c.prop("crate", center, height, size=.92, angle=(0, -11, 5)[beat])
    for dx, color in ((-26, "#9bd9cf"), (26, "#f2aaa4")):
        c.ellipse((center + dx - 3, height + 8, center + dx + 3, height + 15), color)
    if beat != 1:
        c.arrow((center - 10, 215), (center + 31, 215))


def partners_05(c, beat):
    c.stage("hall")
    c.polygon([(212, 133), (300, 134), (319, 184), (213, 182)], "#4c5c69")
    c.line([(225, 145), (311, 166)], "#7b8e96", 2)
    lead_hand = ((194, 159), (181, 111), (182, 112))[beat]
    reach(c, 221, 205, lead_hand, face=-1, look=(105, 97), pose="stand")
    if beat:
        hx, hy = lead_hand
        c.rect((hx - 4, hy - 9, hx + 4, hy + 2), "#efc89b", "#35485a", 1, 3)
        c.line([(hx, hy - 10), (hx, hy - 5)], "#35485a", 1)
    x = (95, 123, 137)[beat]
    c.actor(x, 206, color="rose", pose=("step", "step", "stand")[beat], look=(181, 112))
    if beat < 2:
        c.arrow((x + 16, 216), (x + 38, 216))
    else:
        c.line([(156, 215), (197, 215)], "#9eacaa", 2)


def partners_06(c, beat):
    c.stage("night")
    c.rect((264, 46, 290, 121), "#425162", "#6f8090", 2)
    source = ((152, 137), (174, 135), (190, 139))[beat]
    c.beam(source, (277, 88), width=30, color="#9c8449")
    giver_hand = ((146, 140), (168, 137), (124, 152))[beat]
    receiver_hand = ((195, 159), (182, 139), (185, 141))[beat]
    reach(c, 110, 205, giver_hand, look=(278, 87))
    reach(c, (233, 215, 218)[beat], 207, receiver_hand, color="rose", face=-1,
          look=(source[0], source[1]))
    c.prop("flashlight", *source, size=.92, angle=-21)
    if beat == 0:
        c.arrow((231, 221), (208, 221))


def paths_02(c, beat):
    c.stage("hall", light="dim")
    window(c, (226, 46, 282, 105))
    x = (108, 155, 205)[beat]
    c.actor(x, 204, pose="step", look=(272, 116),
            joints={"foot_front": (22, -1), "foot_back": (-18, -3)})
    column(c, 143, 178, base=217)
    if beat == 0:
        c.arrow((110, 222), (142, 222))
    if beat == 2:
        c.arrow((213, 222), (250, 222))
        c.camera((45, 18, 312, 218))


def paths_03(c, beat):
    c.stage()
    doorway(c, 103, 173, interior="#344354")
    c.polygon([(108, 195), (169, 195), (195, 222), (125, 221)], "#6e6554")
    c.actor((149, 188, 219)[beat], 205, pose=("step", "stand", "look-back")[beat],
            look=((210, 115), (236, 136), (123, 105))[beat])
    if beat == 0:
        c.arrow((159, 216), (190, 216))
    if beat == 1:
        c.ellipse((179, 204, 202, 211), None, "#e9be74", 2)


def paths_04(c, beat):
    c.stage("hall")
    for x in (161, 205, 256, 296):
        c.rect((x - 2, 139, x + 2, 203), "#5d7785")
    c.line([(153, 139), (300, 139)], "#9baeb2", 6)
    c.line([(153, 161), (300, 161)], "#6d8996", 3)
    if beat == 0:
        c.actor(102, 204, pose="step", look=(172, 139))
        c.arrow((103, 217), (138, 217))
    else:
        reach(c, 138, 205, (169, 138), pose="stand", look=(183, 137))
        c.ellipse((166, 135, 173, 142), "#a2dbc9")
        if beat == 2:
            c.camera((103, 65, 238, 167))


def paths_05(c, beat):
    c.stage("studio", light=("backlit", "backlit", "dim")[beat])
    if beat < 2:
        doorway(c, 123, 195, interior="#a59665")
        c.polygon([(131, 196), (181, 196), (223, 219), (101, 219)], "#7f6b4a")
        c.polygon([(148, 200), (161, 199), (175, 219), (144, 219)], "#303745")
        c.actor(157, 205, silhouette=True, look=(215, 117))
        c.rect((123, 49, 129, 196), "#606875")
        if beat == 1:
            c.camera((32, 26, 288, 218))
    else:
        # From inside the same room, the door jamb and cast shadow move in projection together.
        c.polygon([(104, 43), (173, 50), (170, 195), (99, 189)], "#8c8058", "#a4a194", 4)
        c.polygon([(112, 190), (169, 195), (212, 217), (142, 215)], "#6b5e47")
        c.polygon([(140, 199), (153, 198), (182, 217), (164, 216)], "#3d4350")
        c.actor(146, 204, face=-1, pose="stand", look=(92, 124))
        c.line([(104, 43), (99, 189), (171, 195)], "#a6aa9c", 3)


def paths_06(c, beat):
    c.stage("wall")
    c.ellipse((210, 198, 276, 216), "#596656", "#98a582", 1)
    plank = (
        [(125, 36), (186, 42), (184, 63), (125, 56)],
        [(144, 52), (174, 91), (159, 108), (129, 70)],
        [(130, 185), (190, 189), (182, 211), (122, 207)],
    )[beat]
    if beat < 2:
        c.line([(147, 23), (141 + 15 * beat, 45 + 16 * beat)], "#91a0a8", 2)
    c.polygon(plank, "#ad805c", "#e1b987", 2)
    x = (111, 195, 243)[beat]
    c.actor(x, 205, pose=("stand", "step", "stand")[beat],
            look=((154, 51), (237, 194), (173, 191))[beat], face=-1 if beat == 2 else 1)
    if beat == 1:
        c.arrow((188, 221), (223, 221))


SCENES = {
    "performance-01": beats(performance_01),
    "performance-02": beats(performance_02),
    "performance-03": beats(performance_03),
    "performance-04": beats(performance_04),
    "performance-05": beats(performance_05),
    "performance-06": beats(performance_06),
    "partners-01": beats(partners_01),
    "partners-02": beats(partners_02),
    "partners-03": beats(partners_03),
    "partners-04": beats(partners_04),
    "partners-05": beats(partners_05),
    "partners-06": beats(partners_06),
    "paths-01": beats(paths_01),
    "paths-02": beats(paths_02),
    "paths-03": beats(paths_03),
    "paths-04": beats(paths_04),
    "paths-05": beats(paths_05),
    "paths-06": beats(paths_06),
}
