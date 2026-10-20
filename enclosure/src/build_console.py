"""Builds enclosure/console.blend: the pedal in its current case (Hammond 1456RH3 and the
Prechen 8.8" bar screen), on the old model's wood floor in a dark room. A design render, not a drilling template: every
panel position is provisional (console.py says why).

Two scenes share the set:
  Console           the closed pedal on a turntable (it turns once over frames 1-240; frame 1
                    is the hero still), with the hero and front 3/4 cameras;
  Console Exploded  the same parts pulled apart, with labels.

  blender -b --factory-startup -P src/build_console.py"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bl_console as BC  # noqa: E402
import bl_scene as S  # noqa: E402
import bl_util as U  # noqa: E402
import console as C  # noqa: E402

BLEND = os.path.normpath(os.path.join(HERE, "..", "console.blend"))
FONT = "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf"
MM = 0.001
TURN_FRAMES = 240
HERO_YAW = 0.0                    # the turntable's angle at frame 1

# Where each group moves in the exploded view, (towards the rear, up) in mm. The screen comes
# forward as well as up, so it shows in front of the cover rather than hiding under it.
EXPLODE = {"Case": (0.0, 0.0), "Inside": (0.0, 105.0), "Screen": (-95.0, 220.0), "Cover": (0.0, 330.0)}


def groups(M):
    src = U.collection("ConsoleSource")
    g = {k: U.collection("Console_" + k, src) for k in EXPLODE}
    BC.case(g["Case"], M)
    BC.cover(g["Cover"], M)
    BC.panel(g["Cover"], M)
    BC.rear(g["Cover"], M)
    BC.screen(g["Screen"], M)
    BC.stripboards(g["Inside"], M)
    BC.pico(g["Inside"], M)
    BC.kicad_boards(g["Inside"], M)
    for c in g.values():
        c.instance_offset = (C.W / 2, C.D / 2, -C.FOOT_H)
    return src, g


def instance(name, coll, scene_coll, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    e.location = loc
    e.scale = (MM, MM, MM)
    scene_coll.objects.link(e)
    return e


def to_world(p, lift=0.0):
    """Console mm (console.py's frame) to the world, for a pedal centred on the origin."""
    return Vector(((p[0] - C.W / 2) * MM, (p[1] - C.D / 2) * MM, (p[2] + C.FOOT_H + lift) * MM))


def studio(scene, M):
    """The old model's set, as the teaser lights it: a wood floor in a dark room with a little haze,
    two LED tubes behind as practicals. A black box in the dark is drawn by its edges: a narrow cool
    rim from behind and above on the left, a narrow warm kicker low behind the right end raking the
    top, and the bar screen's own light on what is in front of it. A soft light overhead is kept low:
    the screen's anti-glare glass shows it as a sheen."""
    coll = U.collection("Studio")
    S.floor(coll)
    S.world_and_render(scene, samples=256, haze=0.025)
    scene.view_settings.exposure = -0.25
    lights = U.collection("StudioLights", coll)
    # The tubes are the room's: the exploded view leaves them out, so they never sit behind a label.
    prac = U.collection("Practicals", coll)
    M.alu_dark = U.principled("AnodisedAlu", (0.08, 0.08, 0.085), metallic=1, rough=0.35)
    orange, cyan = (1.0, 0.28, 0.03), (0.04, 0.55, 1.0)
    S.tube_light(prac, M, "Tube_Orange", (-0.62, 0.62, 0), orange, strength=1.4, turn=0.4)
    S.tube_light(prac, M, "Tube_Cyan", (0.78, 0.7, 0), cyan, strength=1.3, turn=-0.3)
    # The tubes' light on the pedal and the floor: thin areas beside them, unseen by the camera.
    # Deep blue rather than the tube's cyan, as in the old set.
    S.area(prac, "Tube_Orange_Light", (-0.59, 0.58, 0.05), (0.0, 0.0, 0.03), (0.035, 0.3), 9.0, rgb=orange)
    S.area(prac, "Tube_Blue_Light", (0.75, 0.66, 0.05), (0.0, 0.0, 0.03), (0.035, 0.3), 6.0, rgb=(0.02, 0.16, 1.0))
    centre = to_world((C.W / 2, C.D / 2, 40.0))
    rim = S.area(lights, "Rim", centre + Vector((-0.75, 0.95, 0.3)), centre, (0.35, 0.2), 14.0, rgb=(0.7, 0.82, 1.0))
    rim.data.spread = math.radians(35)
    kick = S.area(lights, "Kicker", to_world((C.W / 2 + 520.0, C.D / 2 + 380.0, 140.0)),
                  to_world((C.W / 2, 120.0, 70.0)), (0.06, 0.06), 6.0, rgb=(1.0, 0.5, 0.2))
    kick.data.spread = math.radians(30)
    # A warm spot from the front left, as the old set's Fresnel: a pool on the floor that the pedal
    # sits in, falling off to dark.
    sp = bpy.data.lights.new("Pool", "SPOT")
    sp.energy, sp.color = 30.0, (1.0, 0.78, 0.55)
    sp.spot_size, sp.spot_blend, sp.shadow_soft_size = math.radians(42), 0.9, 0.08
    po = bpy.data.objects.new("Pool", sp)
    lights.objects.link(po)
    loc = Vector((-0.75, -0.65, 1.1))
    po.matrix_world = Matrix.Translation(loc) @ (Vector((0.05, 0.1, 0.0)) - loc).to_track_quat("-Z", "Y").to_matrix().to_4x4()
    # The screen lights what is in front of it: the footswitches, the knobs, the slope's foot.
    sc = to_world(C.slope_point(C.CX, C.SCREEN_S))
    sn = Vector((0.0, -math.sin(math.radians(C.SLOPE)), math.cos(math.radians(C.SLOPE))))
    S.area(lights, "ScreenGlow", sc + sn * 0.01, sc + sn, (0.2, 0.05), 1.5, rgb=(0.85, 0.7, 0.55))
    # Soft light for the panel's detail, on the pedal only (main() links it and the rim), so the
    # floor round it stays dark and the pools of the tubes and the kicker are all that shows of it.
    key = S.area(lights, "Key_Top", (-0.15, -0.5, 0.95), (0.0, 0.0, 0.03), (0.9, 0.6), 10.0, rgb=(1.0, 0.95, 0.88))
    fill = S.area(lights, "Fill_Front", (-0.35, -0.95, 0.3), (0.0, 0.0, 0.03), (0.6, 0.35), 4.0,
                  rgb=(1.0, 0.93, 0.85))
    return coll, (rim, key, fill)


def copy_render(src, dst):
    dst.world = src.world
    dst.render.engine = "CYCLES"
    for k in ("device", "samples", "use_adaptive_sampling", "adaptive_threshold", "use_denoising", "denoiser",
              "max_bounces", "glossy_bounces", "transmission_bounces", "caustics_reflective",
              "caustics_refractive", "use_light_tree", "volume_step_rate", "volume_max_steps"):
        setattr(dst.cycles, k, getattr(src.cycles, k))
    for k in ("resolution_x", "resolution_y", "resolution_percentage"):
        setattr(dst.render, k, getattr(src.render, k))
    dst.view_settings.view_transform = src.view_settings.view_transform
    dst.view_settings.look = src.view_settings.look
    dst.view_settings.exposure = src.view_settings.exposure
    dst.render.image_settings.file_format = "PNG"
    dst.render.image_settings.color_depth = "8"


# ---- Labels -------------------------------------------------------------------------------------

def label_mats():
    def emit(name, rgb, strength):
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs[0].default_value = (*rgb, 1)
        e.inputs[1].default_value = strength
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(e.outputs[0], o.inputs[0])
        return m
    return emit("LabelText", (1.0, 1.0, 1.0), 1.6), emit("LabelLine", (1.0, 0.45, 0.15), 1.4)


class Labeller:
    """Text and leader lines on a plane just in front of a camera, so they are never hidden and
    keep one size on screen. Positions are given in the frame: (u, v), 0..1 from bottom-left."""

    def __init__(self, coll, cam, scene, depth=0.25):
        self.coll, self.cam, self.scene, self.depth = coll, cam, scene, depth
        self.text_mat, self.line_mat = label_mats()
        self.font = bpy.data.fonts.load(FONT, check_existing=True)
        c = cam.data
        r = scene.render
        self.aspect = r.resolution_y / r.resolution_x
        self.k = c.lens / c.sensor_width          # sensor fit is horizontal (landscape frame)
        self.half_w = depth / (2 * self.k)
        self.mw = Matrix.LocRotScale(cam.location, cam.rotation_euler.to_quaternion(), Vector((1, 1, 1)))
        self.inv = self.mw.inverted()
        self.rot = self.mw.to_quaternion().to_matrix().to_4x4()

    def at(self, u, v, depth=None):
        d = self.depth if depth is None else depth
        hw = self.half_w * d / self.depth
        return self.mw @ Vector(((u - 0.5) * 2 * hw, (v - 0.5) * 2 * hw * self.aspect, -d))

    def uv(self, p):
        q = self.inv @ Vector(p)
        return 0.5 + self.k * q.x / -q.z, 0.5 + self.k * q.y / -q.z / self.aspect

    def text(self, s, u, v, size=0.016, align="LEFT", name=None):
        cu = bpy.data.curves.new("label", "FONT")
        cu.body = s
        cu.font = self.font
        cu.size = size * self.half_w * 2
        cu.align_x = align
        cu.align_y = "CENTER"
        o = bpy.data.objects.new(name or ("Label_" + s[:24]), cu)
        self.coll.objects.link(o)
        o.data.materials.append(self.text_mat)
        o.matrix_world = Matrix.Translation(self.at(u, v)) @ self.rot
        o.visible_shadow = False
        return o

    def line(self, a, b, r=0.0005, name="Leader"):
        """A thin rod from a to b (world), scaled to stay ~1.5 px wide."""
        bm = bmesh.new()
        v = b - a
        m = Matrix.Translation(a) @ v.to_track_quat("Z", "Y").to_matrix().to_4x4()
        U.cyl(bm, r * self.half_w * 2, 0.0, v.length, seg=8, matrix=m)
        me = U.mesh_from_bm(bm, name)
        o = U.new_obj(name, me, self.coll, mat=self.line_mat)
        o.visible_shadow = False
        return o

    def callout(self, s, anchor, u, v, side="left", size=0.016):
        """A label at (u, v), at the frame's edge, with a leader from its inner end to where the
        world point anchor appears. The leader lies in the label plane, so nothing hides it."""
        au, av = self.uv(anchor)
        width = len(s) * 0.52 * size            # DIN Alternate Bold, near enough
        gap = 0.008
        if side == "left":
            self.text(s, u, v, size=size, align="LEFT")
            start = u + width + gap
        else:
            self.text(s, u, v, size=size, align="RIGHT")
            start = u - width - gap
        p_seen = self.at(au, av)
        self.line(self.at(start, v), p_seen)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.0028 * self.half_w * 2,
                                  matrix=Matrix.Translation(p_seen))
        me = U.mesh_from_bm(bm, "LeaderDot")
        o = U.new_obj("LeaderDot", me, self.coll, mat=self.line_mat)
        o.visible_shadow = False


def exploded_labels(scene, cam, inst_z):
    coll = U.collection("Labels", scene.collection)
    L = Labeller(coll, cam, scene)

    def at(p, group):
        dy, dz = inst_z[group]
        return to_world((p[0], p[1] + dy, p[2]), dz)

    sx = C.CX
    callouts = [
        # (text, anchor (mm, group), label u, v, side)
        ("Hammond 1456RH3 cover, 2 mm aluminium", ((30.0, C.D - 25.0, C.H), "Cover"), 0.03, 0.93, "left"),
        ("Six footswitches", ((C.FOOTSWITCHES[0][0], 30.0, 52.0), "Cover"), 0.03, 0.80, "left"),
        ("Out volume, rotary, apply and back", ((C.VOLUME[0], 125.0, 72.0), "Cover"), 0.97, 0.93, "right"),
        ('Prechen 8.8" touch screen, 1920 x 480', ((sx + 90.0, 90.0, 52.0), "Screen"), 0.97, 0.64, "right"),
        ("Raspberry Pi 5", ((C.PI5[0] + 40.0, C.PI5[1] + 28.0, 20.0), "Inside"), 0.03, 0.52, "left"),
        ("Pico 2", ((C.PICO[0] + 10.0, C.PICO[1] + 25.0, 12.0), "Inside"), 0.03, 0.42, "left"),
        ("WM8960 codec", ((C.CODEC[0] + 12.0, C.CODEC[1] + 20.0, 12.0), "Inside"), 0.97, 0.28, "right"),
        ("Input board", ((C.BOARDS["input-buffer"][0] + 90.0, C.BOARDS["input-buffer"][1] + 18.0, 14.0), "Inside"),
         0.97, 0.50, "right"),
        ("Output boards L and R", ((C.BOARDS["output-r"][0] + 20.0, C.BOARDS["output-r"][1] + 14.0, 14.0), "Inside"),
         0.97, 0.40, "right"),
        ("Case: base and end panels", ((60.0, 30.0, 1.0), "Case"), 0.03, 0.20, "left"),
    ]
    for s, (p, g), u, v, side in callouts:
        L.callout(s, at(p, g), u, v, side)
    L.text("DESIGN RENDER  /  PANEL LAYOUT PROVISIONAL, NOT FOR DRILLING", 0.5, 0.035, size=0.0145, align="CENTER",
           name="Label_Caption")
    return coll


# ---- Build --------------------------------------------------------------------------------------

def main():
    U.reset()
    M = BC.materials(U.Mats())
    sc = bpy.context.scene
    sc.name = "Console"
    src, g = groups(M)
    bpy.context.view_layer.layer_collection.children["ConsoleSource"].exclude = True
    st, pedal_lights = studio(sc, M)

    # The closed pedal, on a turntable.
    asm = U.collection("Console_Assembled_All", src)
    for c in g.values():
        asm.children.link(c)
    asm.instance_offset = (C.W / 2, C.D / 2, -C.FOOT_H)
    ped = instance("Console", asm, sc.collection)
    fc = ped.driver_add("rotation_euler", 2)
    fc.driver.type = "SCRIPTED"
    fc.driver.expression = f"{HERO_YAW} + (frame - 1) * 2 * pi / {TURN_FRAMES}"
    sc.frame_start, sc.frame_end = 1, TURN_FRAMES
    sc.frame_set(1)

    cams = U.collection("Cameras", sc.collection)
    centre = to_world((C.W / 2, C.D / 2 + 5.0, 40.0))
    S.camera(cams, "CON_1_Hero", (-0.55, -0.88, 0.48), centre, lens=70, fstop=7.1)
    screen_c = to_world(C.slope_point(C.CX, C.SCREEN_S))
    S.camera(cams, "CON_3_Front34", (0.36, -0.50, 0.27), to_world(C.slope_point(C.CX + 30.0, 70.0)), lens=50,
             fstop=4.5, focus=screen_c)
    sc.camera = bpy.data.objects["CON_1_Hero"]

    # The exploded pedal, in its own scene with the same studio.
    ex = bpy.data.scenes.new("Console Exploded")
    copy_render(sc, ex)
    for o in st.objects:
        ex.collection.objects.link(o)
    for c in st.children:
        if c.name != "Practicals":
            ex.collection.children.link(c)
    exc = U.collection("Exploded", ex.collection)
    inst_z = {}
    lit = [ped]
    for k, c in g.items():
        inst_z[k] = EXPLODE[k]
        lit.append(instance("Exploded_" + k, c, exc, loc=(0, EXPLODE[k][0] * MM, EXPLODE[k][1] * MM)))
    for light in pedal_lights:
        S.link_to(light, lit, "PedalOnly")
    ecams = U.collection("ExplodedCameras", ex.collection)
    cam = S.camera(ecams, "CON_2_Exploded", (-0.72, -1.22, 1.0), to_world((C.W / 2, C.D / 2, 175.0)), lens=50,
                   fstop=11.0)
    cam.data.dof.use_dof = False                # the labels sit just in front of the lens
    ex.camera = cam
    win = bpy.context.window
    if win is not None:
        win.scene = ex
    exploded_labels(ex, cam, inst_z)

    for img in bpy.data.images:
        if img.source == "FILE":
            img.pack()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print("SAVED", BLEND)


if __name__ == "__main__":
    main()
