"""Small drawing language for consistent 4:3 previsualization panels."""

from math import atan2, cos, hypot, radians, sin

from PIL import Image, ImageDraw


WIDTH, HEIGHT = 320, 240
PALETTE = {
    "ink": "#27394a", "dark": "#233140", "navy": "#263846", "slate": "#586c80",
    "muted": "#627787", "line": "#8fa1a8", "grid": "#c3c9c5", "paper": "#ebeadf",
    "wall": "#e4e4d8", "floor": "#d9dfd8", "light": "#f9f2d9", "white": "#fffaf0",
    "sun": "#ffe09a", "gold": "#edba58", "gold-dark": "#986022", "teal": "#138a82",
    "blue": "#487bb0", "rose": "#bb6b63", "violet": "#82699f",
    "arrow": "#617c91", "orange": "#d68143", "green": "#6e9a7a", "red": "#b65e55",
    "skin": "#f0c898", "stone": "#b8c5c1", "gray": "#a1acac", "black": "#1d2735",
}
NEUTRAL = {
    "head": (0, -126), "neck": (0, -112), "shoulder": (1, -105), "hip": (0, -66),
    "elbow_front": (13, -86), "hand_front": (15, -67),
    "elbow_back": (-11, -84), "hand_back": (-13, -64),
    "knee_front": (9, -34), "foot_front": (12, -2),
    "knee_back": (-10, -33), "foot_back": (-12, -2),
}
POSES = {
    "stand": {},
    "step": {"hip": (1, -65), "shoulder": (4, -103), "head": (7, -124),
             "elbow_front": (0, -87), "hand_front": (-9, -68), "elbow_back": (13, -82),
             "hand_back": (22, -72), "knee_front": (16, -33), "foot_front": (33, -2),
             "knee_back": (-18, -34), "foot_back": (-29, -8)},
    "reach": {"shoulder": (5, -103), "head": (9, -124), "elbow_front": (23, -91), "hand_front": (42, -86)},
    "crouch": {"head": (11, -96), "neck": (7, -82), "shoulder": (4, -76), "hip": (-8, -39),
               "elbow_front": (23, -62), "hand_front": (35, -61), "elbow_back": (-15, -60),
               "hand_back": (-19, -42), "knee_front": (19, -24), "foot_front": (25, -2),
               "knee_back": (-25, -20), "foot_back": (-25, -2)},
    "sit": {"head": (5, -106), "neck": (3, -93), "shoulder": (3, -87), "hip": (-4, -47),
            "elbow_front": (15, -66), "hand_front": (23, -48), "elbow_back": (-16, -72),
            "hand_back": (-13, -49), "knee_front": (26, -43), "foot_front": (27, -2),
            "knee_back": (14, -40), "foot_back": (12, -2)},
    "half-rise": {"head": (14, -115), "neck": (10, -100), "shoulder": (8, -94),
                  "hip": (-8, -52), "elbow_front": (24, -76), "hand_front": (32, -58),
                  "elbow_back": (-12, -72), "hand_back": (-18, -51), "knee_front": (15, -31),
                  "foot_front": (24, -2), "knee_back": (-15, -29), "foot_back": (-14, -2)},
    "bend": {"head": (30, -91), "neck": (21, -84), "shoulder": (17, -79), "hip": (-7, -55),
             "elbow_front": (25, -59), "hand_front": (36, -38), "elbow_back": (7, -60),
             "hand_back": (14, -42), "knee_front": (12, -33), "knee_back": (-13, -31)},
    "look-back": {"head": (-8, -125), "neck": (-3, -110), "shoulder": (0, -103),
                  "hip": (2, -65), "elbow_front": (18, -87), "hand_front": (18, -69),
                  "knee_front": (13, -33), "foot_front": (21, -2), "foot_back": (-18, -2)},
    "carry": {"elbow_front": (20, -84), "hand_front": (29, -76),
              "elbow_back": (11, -86), "hand_back": (25, -91)},
    "raise": {"head": (1, -127), "elbow_front": (21, -120), "hand_front": (23, -143),
              "elbow_back": (-9, -88), "hand_back": (-10, -71)},
}


def pigment(color):
    """Accept the storyboard palette, a Pillow color string, or an RGB(A) tuple."""
    return PALETTE.get(color, color) if isinstance(color, str) else color


def rgb(color):
    value = pigment(color)
    if isinstance(value, str) and value.startswith("#") and len(value) == 7:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    if isinstance(value, str):
        from PIL import ImageColor

        return ImageColor.getrgb(value)[:3]
    return value[:3]


def blend(color, other, strength):
    return tuple(round(a + (b - a) * strength) for a, b in zip(rgb(color), rgb(other)))


class Canvas:
    """Stores a supersampled image while letting art scripts use logical pixels."""

    def __init__(self, scale=2):
        self.scale = scale
        self.image = Image.new("RGB", (WIDTH * scale, HEIGHT * scale), PALETTE["paper"])
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def point(self, point):
        return tuple(round(value * self.scale) for value in point)

    def _box(self, box):
        return tuple(round(value * self.scale) for value in box)

    def rect(self, box, fill, outline=None, width=1, radius=0):
        style = {
            "fill": pigment(fill), "outline": pigment(outline), "width": max(1, round(width * self.scale)),
        }
        if radius:
            self.draw.rounded_rectangle(self._box(box), radius=round(radius * self.scale), **style)
        else:
            self.draw.rectangle(self._box(box), **style)

    def ellipse(self, box, fill, outline=None, width=1):
        self.draw.ellipse(self._box(box), fill=pigment(fill), outline=pigment(outline),
                          width=max(1, round(width * self.scale)))

    def line(self, points, fill, width=2):
        self.draw.line([self.point(point) for point in points], fill=pigment(fill),
                       width=max(1, round(width * self.scale)), joint="curve")

    def polygon(self, points, fill, outline=None, width=1):
        vertices = [self.point(point) for point in points]
        self.draw.polygon(vertices, fill=pigment(fill), outline=pigment(outline))
        if outline and width > 1:
            self.draw.line(vertices + [vertices[0]], fill=pigment(outline), width=round(width * self.scale), joint="curve")

    def arrow(self, start, end, color="arrow", width=2):
        distance = hypot(end[0] - start[0], end[1] - start[1])
        if distance <= 3:
            return
        angle = atan2(end[1] - start[1], end[0] - start[0])
        cap = min(distance * .45, 9 + width * 1.3)
        self.line((start, end), color, width)
        self.polygon((end, (end[0] - cap * cos(angle + .43), end[1] - cap * sin(angle + .43)),
                      (end[0] - cap * cos(angle - .43), end[1] - cap * sin(angle - .43))), color)

    def beam(self, start, end, width=25, color="sun"):
        length = hypot(end[0] - start[0], end[1] - start[1])
        if not length:
            return
        nx, ny = (start[1] - end[1]) / length, (end[0] - start[0]) / length
        tint = rgb(color)
        for span, opacity in ((1, 45), (.74, 38), (.5, 35), (.24, 22)):
            spread = width * span
            self.polygon(((start[0] + 2 * nx, start[1] + 2 * ny),
                          (end[0] + spread * nx, end[1] + spread * ny),
                          (end[0] - spread * nx, end[1] - spread * ny),
                          (start[0] - 2 * nx, start[1] - 2 * ny)), (*tint, opacity))

    def glow(self, x, y, radius, color="sun"):
        tint = rgb(color)
        for multiplier, opacity in ((1, 20), (.79, 30), (.58, 37), (.36, 42), (.16, 52)):
            r = radius * multiplier
            self.ellipse((x - r, y - r, x + r, y + r), (*tint, opacity))

    def stage(self, kind="studio", light="normal"):
        night = kind == "night" or light in {"dim", "backlit"}
        wall = "#435464" if night else "#e3e5dc"
        floor = "#536572" if night else "#d4dcd7"
        horizon = 170
        self.rect((0, 0, WIDTH, HEIGHT), wall)
        side = blend(wall, "ink", .10 if night else .08)
        edge = blend(wall, "ink", .26 if night else .20)
        self.polygon(((0, 0), (23, 0), (47, 37), (47, horizon), (0, 180)), side)
        self.polygon(((320, 0), (285, 0), (267, 37), (267, horizon), (320, 182)), side)
        self.line(((47, 37), (267, 37)), edge, 1)
        self.polygon(((0, 182), (47, horizon), (267, horizon), (320, 183), (320, 240), (0, 240)), floor)
        seam = blend(floor, "ink", .16)
        for x in (9, 61, 115, 160, 205, 259, 310):
            self.line(((160 + (x - 160) * .63, horizon), (x, 240)), seam, .7)
        for y in (183, 203, 228):
            self.line(((0, y), (320, y)), seam, .65)
        self.line(((47, 38), (47, horizon), (267, horizon), (267, 38)), edge, 1.2)
        if kind in {"door", "hall"}:
            self.rect((135, 58, 191, 174), "#b7c2bb" if not night else "#273745", edge, 2, 2)
            self.rect((143, 65, 183, 173), "#d6dcd0" if not night else "#75808a")
            self.line(((151, 177), (129, 222), (202, 222), (176, 177)), blend(floor, "white", .31), 1.2)
        elif kind == "room":
            self.rect((181, 62, 241, 113), "#b8cfce" if not night else "#839291", edge, 2, 3)
            self.line(((211, 63), (211, 111)), edge, 2)
            self.line(((182, 87), (240, 87)), edge, 2)
            self.rect((172, 111, 245, 116), blend(wall, "ink", .27), radius=1)
        elif kind == "steps":
            for index in range(3):
                x = 176 + index * 23
                y = 202 - index * 12
                self.polygon(((x, y), (319, y), (319, y + 14), (x, y + 14)), blend(floor, "ink", .05 * index), edge)
        elif kind == "wall":
            for y in (73, 101, 129, 157):
                self.line(((48, y), (267, y)), blend(wall, "ink", .11), .7)
        if light == "backlit":
            self.rect((143, 64, 182, 172), "#e8cc90")
            self.polygon(((143, 172), (183, 172), (231, 229), (94, 229)), (255, 218, 148, 66))
        elif not night:
            self.polygon(((54, 42), (88, 42), (210, 170), (160, 170)), (255, 251, 226, 37))
        self.rect((0, 0, WIDTH - 1, HEIGHT - 1), None, blend(wall, "ink", .26), .8)

    def actor(self, x, y=206, *, color="teal", pose="stand", face=1, scale=1, joints=None,
              look=None, silhouette=False):
        local = {**NEUTRAL, **POSES[pose], **(joints or {})}
        points = {name: (x + dx * face * scale, y + dy * scale) for name, (dx, dy) in local.items()}
        head, neck, shoulder, hip = (points[name] for name in ("head", "neck", "shoulder", "hip"))
        eye_line = face if look is None else look
        vertical_gaze = 0
        if isinstance(look, tuple):
            eye_line = 1 if look[0] >= head[0] else -1
            vertical_gaze = max(-2, min(2, (look[1] - head[1]) / 18)) * scale
        ink = rgb("black" if silhouette else "ink")
        fabric = rgb("dark" if silhouette else color)
        shadow = fabric if silhouette else blend(fabric, "ink", .37)
        light = fabric if silhouette else blend(fabric, "white", .20)
        face_color = fabric if silhouette else rgb("skin")
        sole = fabric if silhouette else blend(fabric, "dark", .57)

        def rounded(points_, fill, weight):
            self.line(points_, fill, weight * scale)
            r = weight * scale / 2
            for ax, ay in points_:
                self.ellipse((ax - r, ay - r, ax + r, ay + r), fill)

        def limb(joint_names, outer, inner, weight):
            path = [points[name] for name in joint_names]
            rounded(path, outer, weight + 2.6)
            rounded(path, inner, weight)

        feet = [points[f"foot_{side}"] for side in ("back", "front")]
        if not silhouette:
            for fx, fy in feet:
                self.ellipse((fx - 17 * scale, fy - 1, fx + 25 * scale, fy + 7 * scale), (29, 41, 46, 38))
        for side, shade in (("back", shadow), ("front", fabric)):
            limb(("hip", f"knee_{side}", f"foot_{side}"), ink, shade, 12.2)
            fx, fy = points[f"foot_{side}"]
            rounded(((fx - 2 * face * scale, fy), (fx + 9 * face * scale, fy + 1 * scale)), ink, 8.2)
            rounded(((fx - 1 * face * scale, fy), (fx + 8 * face * scale, fy)), sole, 5.6)
        limb(("shoulder", "elbow_back", "hand_back"), ink, shadow, 9)
        shx, shy = shoulder
        hx, hy = hip
        self.polygon(((shx - 14 * scale, shy + 2 * scale), (shx - 8 * scale, shy - 8 * scale),
                      (shx + 9 * scale, shy - 8 * scale), (shx + 15 * scale, shy - 1 * scale),
                      (hx + 10 * scale, hy + 3 * scale), (hx - 11 * scale, hy + 3 * scale)),
                     fabric, ink, 1.2)
        if not silhouette:
            self.polygon(((shx - 9 * scale, shy - 5 * scale), (shx + 5 * scale, shy - 5 * scale),
                          (hx + 5 * scale, hy - 5 * scale), (hx - 3 * scale, hy - 4 * scale)), light)
            self.line(((hx - 8 * scale, hy - 4 * scale), (hx + 8 * scale, hy - 4 * scale)), shadow, 1.5 * scale)
        rounded((neck, (shx, shy - 4 * scale)), ink, 9)
        rounded((neck, (shx, shy - 4 * scale)), face_color, 6.5)
        limb(("shoulder", "elbow_front", "hand_front"), ink, light, 10)
        for hand in (points["hand_front"], points["hand_back"]):
            r = 4.7 * scale
            self.ellipse((hand[0] - r, hand[1] - r, hand[0] + r, hand[1] + r), face_color, ink, 1.15 * scale)
        cx, cy = head
        ax, ay = 11.1 * scale, 13.5 * scale
        self.ellipse((cx - ax, cy - ay, cx + ax, cy + ay), face_color, ink, 1.4 * scale)
        self.polygon(((cx + eye_line * (ax - 1), cy - 3 * scale),
                      (cx + eye_line * (ax + 3 * scale), cy + 1 * scale),
                      (cx + eye_line * (ax - 1), cy + 4 * scale)), face_color)
        if not silhouette:
            self.polygon(((cx - 10 * scale, cy - 7 * scale), (cx - 7 * scale, cy - 12 * scale),
                          (cx + 5 * scale, cy - 13 * scale), (cx + 11 * scale, cy - 8 * scale),
                          (cx + eye_line * 3 * scale, cy - 8 * scale),
                          (cx - eye_line * 6 * scale, cy - 2 * scale)), shadow)
            self.ellipse((cx + eye_line * 6 * scale - 1.35 * scale, cy - 3.1 * scale + vertical_gaze,
                          cx + eye_line * 6 * scale + 1.35 * scale, cy - .3 * scale + vertical_gaze), ink)
        return points

    def camera(self, box):
        self.image = self.image.crop(self._box(box)).resize((WIDTH * self.scale, HEIGHT * self.scale),
                                                           Image.Resampling.LANCZOS)
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def finish(self):
        return self.image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    def prop(self, name, x, y, *, angle=0, size=1, color="gold"):
        """Draw an inert prop outline or a small piece of scenery at its anchor."""
        angle = radians(angle)
        a, b = cos(angle) * size, sin(angle) * size
        base = pigment(color)
        edge = (*rgb("ink"), min(base[3], 200)) if isinstance(base, tuple) and len(base) == 4 else "ink"
        accent = blend(base, "white", .51)
        shading = blend(base, "gold-dark", .41)
        if isinstance(base, tuple) and len(base) == 4:
            accent = (*accent, base[3])
            shading = (*shading, base[3])

        def transform(points):
            return [(x + a * px - b * py, y + b * px + a * py) for px, py in points]

        def poly(points, fill=base, outline=edge, width=1.12):
            self.polygon(transform(points), fill, outline, width * size)

        def stroke(points, fill=edge, width=1.5):
            self.line(transform(points), fill, width * size)

        def box(coords, fill=base, outline=edge):
            x1, y1, x2, y2 = coords
            poly(((x1, y1), (x2, y1), (x2, y2), (x1, y2)), fill, outline)

        def capsule(x1, y1, x2, y2, breadth, fill=base):
            points = transform(((x1, y1), (x2, y2)))
            for color_, weight in ((edge, (breadth + 2) * size), (fill, breadth * size)):
                self.line(points, color_, weight)
                radius = weight / 2
                for px, py in points:
                    self.ellipse((px - radius, py - radius, px + radius, py + radius), color_)

        if name in {"parcel", "letter", "envelope", "note"}:
            box((-10, -6.5, 10, 6.5))
            stroke(((-9, -5), (0, .5), (9, -5)), shading)
            stroke(((-8, 5), (-2, .5)), accent, .9)
        elif name in {"flashlight", "torch"}:
            capsule(-10, 0, 7, 0, 7)
            poly(((4, -4), (13, -6), (13, 6), (4, 4)), shading)
            stroke(((12, -5), (12, 5)), accent, 2.2)
        elif name in {"radio", "phone"}:
            box((-6.5, -12, 6.5, 12))
            box((-4.6, -9, 4.6, 6), accent)
            stroke(((-2.4, 8), (2.4, 8)), shading, 1)
            if name == "radio":
                stroke(((4, -11), (4, -22)), edge, 2)
                stroke(((-3, -3), (3, -3)), shading)
                stroke(((-3, 0), (3, 0)), shading)
        elif name in {"case", "crate", "box"}:
            wide, tall = (24, 15) if name == "case" else (31, 19)
            if name == "case":
                stroke(((-6, -tall), (-6, -tall - 6), (6, -tall - 6), (6, -tall)), edge, 2.6)
            box((-wide, -tall, wide, tall))
            poly(((-wide, -tall), (wide, -tall), (wide - 4, -tall + 4), (-wide + 4, -tall + 4)), accent, None)
            if name == "case":
                box((-wide * .3, -1, -wide * .15, 5), shading, None)
                box((wide * .15, -1, wide * .3, 5), shading, None)
                box((wide * .46, 4, wide * .76, 10), accent, None)
            else:
                stroke(((-wide + 5, -tall + 5), (wide - 5, tall - 5)), shading, 2.4)
                stroke(((-wide + 5, tall - 5), (wide - 5, -tall + 5)), shading, 2.4)
        elif name in {"glass", "cup"}:
            poly(((-7, -10), (7, -10), (5, 10), (-5, 10)))
            stroke(((-6, -8), (6, -8)), accent, 1.6)
            stroke(((-4, 7), (4, 7)), shading, 1)
        elif name in {"fan", "closed-fan"}:
            if name == "closed-fan":
                capsule(0, 0, 20, -19, 4)
            else:
                spokes = [(28 * cos(radians(theta)), 28 * sin(radians(theta)))
                          for theta in range(-158, -21, 17)]
                poly([(0, 0), *spokes])
                for tip in spokes:
                    stroke(((0, 0), tip), shading, .9)
                stroke(spokes, accent, 2)
        elif name == "shield":
            poly(((-17, -23), (0, -27), (17, -23), (16, 11), (8, 21), (0, 26),
                  (-8, 21), (-16, 11)))
            poly(((-11, -19), (0, -22), (11, -19), (10, 9), (0, 18), (-10, 9)), shading)
            stroke(((0, -17), (0, 12)), accent, 1)
        elif name in {"saber", "sword", "scabbard"}:
            capsule(-14, 0, 6, 0, 4.6, shading)
            if name == "saber":
                poly(((7, -3), (37, -3), (61, -8), (52, 1), (29, 7), (7, 4)))
                stroke(((10, -1), (34, -1), (49, -4)), accent, 1.15)
            elif name == "sword":
                poly(((7, -4), (52, -4), (61, 0), (52, 4), (7, 4)))
                stroke(((11, 0), (54, 0)), accent, 1.3)
                capsule(7, -9, 7, 9, 3.2, shading)
            else:
                capsule(5, 0, 53, 0, 7.8, shading)
                capsule(52, 0, 56, 0, 7.8)
                stroke(((6, -5), (6, 5)), accent, 2)
        elif name in {"spear", "halberd", "staff"}:
            capsule(-53, 0, 54, 0, 3.6, shading)
            stroke(((-49, -.8), (54, -.8)), accent, .8)
            if name == "spear":
                poly(((51, -1), (62, -6), (76, 0), (62, 6), (51, 1)))
                stroke(((56, 0), (73, 0)), accent, 1.2)
            if name == "halberd":
                poly(((43, 0), (50, -3), (48, -15), (58, -13), (68, -16), (70, -6),
                      (66, 3), (54, 6), (43, 3)))
                stroke(((49, -10), (61, -10), (66, -12)), accent, 1.2)
            if name == "staff":
                capsule(-53, 0, -48, 0, 5)
                capsule(48, 0, 54, 0, 5)
        elif name == "firearm":
            # Only the external silhouette of a solid inert film prop.
            poly(((-20, -4), (-10, -7), (26, -7), (26, 1), (7, 1), (2, 9),
                  (-4, 9), (-2, 1), (-20, 4)))
            box((23, -6, 26, 0), accent, None)
        elif name == "door":
            box((-27, -118, 27, 0), shading)
            box((-23, -113, 24, -1))
            box((-19, -108, 20, -6), accent)
            stroke(((-25, -118), (-25, 0), (27, 0)), edge, 1.5)
            capsule(14, -53, 18, -53, 2.5, shading)
        elif name == "chair":
            capsule(-15, -68, -15, -4, 4, shading)
            capsule(15, -34, 15, -4, 4, shading)
            poly(((-17, -39), (19, -39), (23, -33), (-18, -33)))
            box((-19, -68, -13, -43))
        elif name == "table":
            capsule(-43, 3, -43, 51, 4.3, shading)
            capsule(43, 3, 43, 51, 4.3, shading)
            poly(((-49, -6), (49, -6), (55, 1), (54, 7), (-54, 7), (-55, 1)))
            stroke(((-52, 1), (51, 1)), accent, 1.45)
        elif name == "railing":
            for offset in (-45, 0, 45):
                capsule(offset, -51, offset, -3, 3, shading)
            capsule(-55, -53, 55, -53, 4.3)
            stroke(((-53, -30), (53, -30)), shading)
        else:
            raise ValueError(f"Unknown storyboard prop {name!r}")
