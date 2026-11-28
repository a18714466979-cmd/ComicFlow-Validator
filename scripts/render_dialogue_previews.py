"""Render the original dialogue cards from the same actor/camera layout as their maps.

Run 'python -m scripts.render_dialogue_previews' with Blender and Pillow installed.
"""
from math import atan2, cos, hypot, pi, sin
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "assets" / "dialogue_previews"
SIZE = (960, 540)
COLORS = {
    "A": ("#32746d", "#1d4c48", "#e5ae84", "#35332f"),
    "B": ("#a85d47", "#703f36", "#d6a185", "#633a26"),
    "C": ("#ac7a2c", "#745124", "#b9825b", "#332925"),
}
PAIR = {"A": (-1.13, 0), "B": (1.13, 0)}
TRIANGLE = {"A": (-1.21, -.15), "B": (1.21, -.15), "C": (0, 1.08)}
CARDS = (
    (PAIR, (
        ((0, -5.45, 1.87), (0, 0, 1.65), 62, {"A": "B", "B": "A"}, "A"),
        ((0, -5.45, 1.87), (0, 0, 1.65), 62, {"A": "B", "B": "A"}, "B"),
    )),
    (PAIR, (
        ((-1.96, -.68, 1.79), (.49, .33, 1.70), 49, {"A": "B", "B": "A"}, "B"),
        ((1.96, -.68, 1.79), (-.49, .33, 1.70), 49, {"A": "B", "B": "A"}, "A"),
    )),
    (TRIANGLE, (
        ((0, -5.62, 1.91), (0, .15, 1.50), 53, {"A": "B", "B": "A", "C": "A"}, "A"),
        ((0, -5.62, 1.91), (0, .15, 1.72), 65, {"A": "C", "B": "C", "C": "B"}, "C"),
    )),
)


def direction(origin, target):
    return atan2(target[1] - origin[1], target[0] - origin[0])


def make_maps():
    from PIL import Image, ImageDraw, ImageFont

    font_candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    )
    font_path = next((candidate for candidate in font_candidates if Path(candidate).is_file()), None)
    label = ImageFont.truetype(font_path, 27) if font_path else ImageFont.load_default(size=27)
    tag = ImageFont.truetype(font_path, 21) if font_path else ImageFont.load_default(size=21)
    ivory = "#fcf6e9"
    edge = "#d7caba"
    camera_ink = "#644b64"

    def arrow(draw, origin, target, fill, *, width=4, head=11, hollow=False):
        heading = direction(origin, target)
        left = (target[0] - head * cos(heading - .5), target[1] - head * sin(heading - .5))
        right = (target[0] - head * cos(heading + .5), target[1] - head * sin(heading + .5))
        draw.line((origin, target), width=width, fill=fill)
        if hollow:
            draw.line((left, target, right), width=width, fill=fill)
        else:
            draw.polygon((target, left, right), fill=fill)

    def dash(draw, a, b, fill, width=2):
        span = hypot(b[0] - a[0], b[1] - a[1])
        for dist in range(0, int(span), 14):
            def progress(length):
                return tuple(u + (v - u) * length / span for u, v in zip(a, b))
            draw.line((progress(dist), progress(min(span, dist + 7))), fill=fill, width=width)

    def viewpoint(d, index, cast, shots, center):
        scale_x, scale_y, depth = ((125, 55, 141), (147, 147, 209), (63, 63, 128))[index]

        def viewport(point):
            return (int(center + point[0] * scale_x), int(depth - point[1] * scale_y))

        pos = {actor: viewport(point) for actor, point in cast.items()}
        ax, ay = pos["A"]
        bx, by = pos["B"]
        extension = 45 if index == 2 else 98
        dash(d, (ax - extension, ay), (bx + extension, by), "#a68f7e", 3)
        if "C" in pos:
            for actor in "AB":
                dash(d, pos[actor], pos["C"], "#baa99a")
        rendered_cameras = set()
        for shot_no, (eye, target, lens, _looks, _speaker) in shots:
            camera = viewport(eye)
            if camera in rendered_cameras:
                continue
            rendered_cameras.add(camera)
            x, y = camera
            camera_badge = "1/2" if index == 0 else str(shot_no)
            aim = viewport(target)
            theta = direction(camera, aim)
            angle = atan2(18, lens)
            length = 165 if index == 1 else 140
            wings = (
                x + length * cos(theta - angle), y + length * sin(theta - angle),
                x + length * cos(theta + angle), y + length * sin(theta + angle),
            )
            d.polygon((camera, (wings[0], wings[1]), (wings[2], wings[3])), fill="#ece2ec")
            ray = length - 15
            pointing = (x + ray * cos(theta), y + ray * sin(theta))
            origin = (x + 19 * cos(theta), y + 19 * sin(theta))
            if index == 1:
                dash(d, origin, aim, camera_ink, 2)
                head_start = (aim[0] - 28 * cos(theta), aim[1] - 28 * sin(theta))
                arrow(d, head_start, aim, camera_ink, width=3, hollow=True)
            else:
                arrow(d, origin, pointing, camera_ink, width=3, hollow=True)
            d.rounded_rectangle((x - 28, y - 22, x + 28, y + 22), radius=6, fill=camera_ink)
            d.text((x, y), camera_badge, font=tag, fill="white", anchor="mm")
        for actor, target in shots[0][1][3].items():
            point, aim = pos[actor], pos[target]
            theta = direction(point, aim)
            perpendicular = theta - pi / 2
            offset = 8 if index == 2 else 19
            offset_x, offset_y = offset * cos(perpendicular), offset * sin(perpendicular)
            origin = (point[0] + cos(theta) * 31 + offset_x, point[1] + sin(theta) * 31 + offset_y)
            distance = 29 if index == 2 and "C" in (actor, target) else 47
            end = (origin[0] + cos(theta) * distance, origin[1] + sin(theta) * distance)
            arrow(d, origin, end, COLORS[actor][0], width=3, head=10)
        for actor, (x, y) in pos.items():
            radius = 22 if index == 2 else 27
            d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=COLORS[actor][0],
                      outline=COLORS[actor][1], width=2)
            d.text((x, y), actor, font=label, fill="white", anchor="mm")

    for index, (cast, shots) in enumerate(CARDS):
        image = Image.new("RGB", SIZE, "#eee3d4")
        d = ImageDraw.Draw(image)
        d.rounded_rectangle((35, 27, 925, 513), radius=19, fill=ivory, outline=edge, width=2)
        for x in range(67, 925, 33):
            for y in range(50, 514, 33):
                d.ellipse((x - 1, y - 1, x + 1, y + 1), fill="#e4d8c9")
        numbered = list(enumerate(shots, 1))
        if index == 2:
            d.line((480, 48, 480, 491), fill=edge, width=2)
            for center, shot in zip((248, 712), numbered):
                viewpoint(d, index, cast, [shot], center)
        else:
            viewpoint(d, index, cast, numbered, 480)
        image.save(DEST / f"dialogue-{index + 1:02d}-map.webp", "WEBP", quality=91, method=6)


def render_shots(output):
    import bpy
    from mathutils import Vector

    def rgba(code):
        parts = [int(code[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return tuple(((c + .055) / 1.055) ** 2.4 if c >= .04045 else c / 12.92 for c in parts) + (1,)

    materials = {}

    def material(code):
        if code not in materials:
            mat = bpy.data.materials.new(code)
            mat.diffuse_color = rgba(code)
            materials[code] = mat
        return materials[code]

    def appearance(obj, code):
        obj.data.materials.append(material(code))
        for face in obj.data.polygons:
            face.use_smooth = True
        return obj

    def oval(center, axes, color, angle=0):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, location=center)
        obj = bpy.context.object
        obj.scale = axes
        obj.rotation_euler.z = angle
        return appearance(obj, color)

    def tube(a, b, radius, color, taper=1):
        delta = Vector(b) - Vector(a)
        bpy.ops.mesh.primitive_cone_add(vertices=24, radius1=radius, radius2=radius * taper,
                                       depth=delta.length, location=(Vector(a) + Vector(b)) / 2)
        obj = bpy.context.object
        obj.rotation_euler = delta.to_track_quat("Z", "Y").to_euler()
        return appearance(obj, color)

    def block(center, axes, color, bevel=.03):
        bpy.ops.mesh.primitive_cube_add(size=1, location=center)
        obj = bpy.context.object
        obj.dimensions = axes
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if bevel:
            modifier = obj.modifiers.new(name="Rounded edges", type="BEVEL")
            modifier.width = bevel
            modifier.segments = 3
            obj.modifiers.new(name="Face normals", type="WEIGHTED_NORMAL")
        obj.data.materials.append(material(color))
        return obj

    def frame(origin, angle):
        x, y = origin
        fx, fy = cos(angle), sin(angle)
        def place(lateral, forward, height):
            return (x - fy * lateral + fx * forward, y + fx * lateral + fy * forward, height)
        return place

    def actor(key, origin, look, body_look, speaking):
        shirt, shadow, skin, hair = COLORS[key]
        yaw, body_yaw = direction(origin, look), direction(origin, body_look)
        torso, head = frame(origin, body_yaw), frame(origin, yaw)
        body_turn, head_turn = body_yaw - pi / 2, yaw - pi / 2
        body_width = {"A": .26, "B": .247, "C": .235}[key]
        eyes_z = {"A": 1.895, "B": 1.885, "C": 1.86}[key]

        oval(torso(0, 0, 1.285), (body_width - .02, .156, .360), shirt, body_turn)
        oval(torso(0, -.01, 1.435), (body_width, .167, .212), shirt, body_turn)
        oval(torso(0, 0, 1.043), (body_width - .043, .143, .205), shadow, body_turn)
        oval(torso(0, .012, 1.59), (.095, .093, .055), shadow, body_turn)
        oval(head(0, 0, 1.66), (.080, .074, .131), skin, head_turn)
        for side in (-1, 1):
            thigh, knee, ankle = (torso(side * .121, -.01, 1.03), torso(side * .141, .02, .52),
                                  torso(side * .138, .017, .135))
            tube(thigh, knee, .121, shadow, .75)
            oval(knee, (.092, .086, .08), shadow, body_turn)
            tube(knee, ankle, .092, shadow, .76)
            oval(torso(side * .139, .081, .09), (.096, .157, .068), "#392f2a", body_turn)
            gesturing = speaking and side == 1
            shoulder = torso(side * (body_width - .016), -.012, 1.485)
            elbow = torso(side * (body_width + .018), .100 if gesturing else -.025, 1.215)
            wrist = torso(side * (body_width + .053), .319 if gesturing else .044, 1.359 if gesturing else .99)
            oval(shoulder, (.107, .101, .162), shirt, body_turn)
            tube(shoulder, elbow, .096, shirt, .72)
            oval(elbow, (.067, .065, .065), skin, body_turn)
            tube(elbow, wrist, .064, skin, .62)
            palm = torso(side * (body_width + .048), .372 if gesturing else .055, 1.38 if gesturing else .947)
            oval(palm, (.050, .067, .038) if gesturing else (.044, .051, .064), skin, body_turn)
            if gesturing:
                oval(torso(side * (body_width + .091), .377, 1.41), (.027, .032, .042), skin, body_turn)

        oval(head(0, 0, eyes_z - .018), (.154, .153, .207), skin, head_turn)
        oval(head(0, .038, eyes_z - .115), (.115, .107, .101), skin, head_turn)
        oval(head(0, .001, eyes_z + .120), (.152, .154, .096), hair, head_turn)
        oval(head(0, -.065, eyes_z + .041), (.150, .101, .151 if key != "C" else .130), hair, head_turn)
        if key == "B":
            oval(head(.069, -.113, eyes_z - .015), (.122, .092, .085), hair, head_turn)
            oval(head(.08, -.143, eyes_z + .036), (.080, .070, .094), hair, head_turn)
        if key == "C":
            oval(head(0, -.128, eyes_z + .104), (.123, .098, .089), hair, head_turn)
        for side in (-1, 1):
            oval(head(side * .147, -.017, eyes_z - .052), (.034, .038, .058), skin, head_turn)
            oval(head(side * .168, -.008, eyes_z - .059), (.010, .025, .034), "#b57355", head_turn)
            oval(head(side * .059, .137, eyes_z - .001), (.040, .017, .023), "#fff0d9", head_turn)
            oval(head(side * .052, .152, eyes_z - .001), (.017, .008, .018), "#30362f", head_turn)
            oval(head(side * .049, .159, eyes_z + .006), (.005, .003, .005), "#fcf3df", head_turn)
            oval(head(side * .058, .142, eyes_z + .037), (.045, .010, .011), hair, head_turn + side * -.08)
        oval(head(0, .153, eyes_z - .038), (.026, .033, .048), skin, head_turn)
        oval(head(0, .174, eyes_z - .055), (.032, .028, .025), skin, head_turn)
        oval(head(0, .140, eyes_z - .106), (.044, .017, .019 if speaking else .006),
             "#70352f" if speaking else "#9a6151", head_turn)
        if speaking:
            oval(head(0, .154, eyes_z - .099), (.025, .006, .004), "#f2d7bc", head_turn)

    def stage():
        block((0, 0, -.13), (19, 15, .25), "#c8b9a4", 0)
        # Walls perpendicular to each other preserve spatial anchors during reverse angles.
        block((0, 3.9, 2.3), (10.8, .25, 4.6), "#dbcebd", 0)
        for side in (-1, 1):
            block((side * 4.42, .37, 2.3), (.24, 7.15, 4.6), "#c4b49f", 0)
            block((side * 4.25, .38, .15), (.10, 7.15, .28), "#967e65", .015)
        block((0, 3.72, .15), (9, .10, .28), "#a08b72", .015)
        for x in (-2.94, -.99, .96, 2.91):
            block((x, 3.712, 1.814), (1.68, .075, 2.65), "#e4d7c7", .045)
        block((0, 3.565, 2.61), (2.72, .09, 1.58), "#b4a089", .015)
        block((0, 3.505, 2.61), (2.58, .065, 1.44), "#cccdb6", .012)
        for z in (2.09, 2.61, 3.13):
            block((0, 3.454, z), (2.59, .05, .026), "#b4ab91", 0)
        for x in (-.66, 0, .66):
            block((x, 3.443, 2.61), (.026, .065, 1.43), "#b4ab91", 0)

    for idx, (cast, shots) in enumerate(CARDS, 1):
        for frame_no, (eye, aim, lens, looks, speaker) in enumerate(shots, 1):
            bpy.ops.object.select_all(action="SELECT")
            bpy.ops.object.delete(use_global=False)
            stage()
            for role, person in cast.items():
                body_target = "B" if role in "AC" else "A"
                if role == "C":
                    body_target = "A"
                actor(role, person, cast[looks[role]], cast[body_target], role == speaker)
            scene = bpy.context.scene
            bpy.ops.object.camera_add(location=eye)
            scene.camera = bpy.context.object
            scene.camera.rotation_euler = (Vector(aim) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
            scene.camera.data.lens = lens

            scene.render.engine = "BLENDER_WORKBENCH"
            shading = scene.display.shading
            shading.light = "STUDIO"
            shading.studio_light = "paint.sl"
            shading.color_type = "MATERIAL"
            shading.show_shadows = True
            shading.show_cavity = True
            shading.cavity_type = "BOTH"
            shading.cavity_ridge_factor = 1.35
            shading.cavity_valley_factor = 1.15
            shading.curvature_ridge_factor = .9
            shading.curvature_valley_factor = 1
            shading.show_specular_highlight = False
            scene.display.render_aa = "8"
            scene.view_settings.view_transform = "Standard"
            scene.render.resolution_x, scene.render.resolution_y = SIZE
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = "PNG"
            scene.render.filepath = str(output / f"dialogue-{idx:02d}-{frame_no}.png")
            bpy.ops.render.render(write_still=True)


def main():
    if "--" in sys.argv:
        render_shots(Path(sys.argv[sys.argv.index("--") + 1]))
        return
    from PIL import Image

    DEST.mkdir(parents=True, exist_ok=True)
    make_maps()
    with TemporaryDirectory() as temp:
        scratch = Path(temp)
        subprocess.run(["blender", "-b", "-t", "4", "--python-exit-code", "1", "--python", __file__, "--", temp],
                       cwd=ROOT, check=True)
        for source in scratch.glob("*.png"):
            with Image.open(source) as image:
                image.convert("RGB").save(DEST / source.with_suffix(".webp").name, quality=91, method=6)


if __name__ == "__main__":
    main()
