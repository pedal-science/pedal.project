"""Builds enclosure/pedal.blend: the two pedals (closed and open-top) on a wooden floor with
standing lights and a set of cameras.

  blender -b -P build_scene.py"""
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bl_pedal  # noqa: E402
import bl_scene as S  # noqa: E402
import bl_util as U  # noqa: E402
import layout as L  # noqa: E402

BLEND = os.path.normpath(os.path.join(HERE, "..", "pedal.blend"))
GAP = 0.034                     # metres between the two enclosures
FOOT = 3.2                      # mm the rubber feet lift the pedal


def pedal_collections(common, closed_only, open_only):
    src = bpy.data.collections["PedalSource"]
    closed = U.collection("Pedal_Closed", src)
    open_ = U.collection("Pedal_Open", src)
    closed.children.link(common)
    closed.children.link(closed_only)
    open_.children.link(common)
    open_.children.link(open_only)
    for c in (closed, open_):
        c.instance_offset = (L.CX, L.CY, -FOOT)
    return closed, open_


def instance(name, coll, loc, rot_z=0.0):
    e = bpy.data.objects.new(name, None)
    e.instance_type = "COLLECTION"
    e.instance_collection = coll
    e.location = loc
    e.rotation_euler = (0, 0, rot_z)
    e.scale = (0.001, 0.001, 0.001)
    bpy.context.scene.collection.objects.link(e)
    return e


def main():
    U.reset()
    M = U.Mats()
    M.alu_dark = U.principled("AnodisedAlu", (0.08, 0.08, 0.085), metallic=1, rough=0.35)
    M.lens_glow = U.principled("FresnelLens", (1, 1, 1), rough=0.08, transmission=1.0, ior=1.5,
                               emission=(1.0, 0.86, 0.7), emission_strength=6.0)
    M.lens_ring = U.principled("FresnelRing", (1, 1, 1), rough=0.1, transmission=1.0, ior=1.5)
    M.lamp_paint = U.principled("LampPaint", U.srgb("#2c3f5c")[:3], rough=0.42, coat=0.3, coat_rough=0.2)
    M.lamp_fin = U.principled("LampFin", (0.75, 0.76, 0.78), metallic=1, rough=0.35)
    M.panel_glow = U.principled("LampPanel", (0.02, 0.02, 0.02), rough=0.2, emission=(0.35, 0.75, 1.0),
                                emission_strength=6.0)
    M.panel_led = U.principled("LampButtonLED", (0.02, 0.02, 0.02), rough=0.3, emission=(1.0, 0.45, 0.1),
                               emission_strength=8.0)
    common, closed_only, open_only = bl_pedal.build(M)
    closed, open_ = pedal_collections(common, closed_only, open_only)
    vl = bpy.context.view_layer
    vl.layer_collection.children["PedalSource"].exclude = True

    half = L.ENC["W"] / 2000 + GAP / 2
    instance("Pedal_Closed", closed, (-half, 0, 0))
    ped_open = instance("Pedal_Open", open_, (half, 0, 0))

    set_ = U.collection("Set")
    S.floor(set_)
    S.world_and_render(bpy.context.scene, haze=0.1)
    lights = U.collection("Lights", set_)
    orange, cyan = (1.0, 0.28, 0.03), (0.04, 0.55, 1.0)
    S.tube_light(lights, M, "Tube_Orange", (-0.46, 0.26, 0), orange, strength=1.4, turn=0.4)
    S.tube_light(lights, M, "Tube_Cyan", (0.5, 0.3, 0), cyan, strength=1.3, turn=-0.3)
    # The tubes' light on the pedals: long thin area lights beside them, unseen by the camera.
    S.area(lights, "Rim_Orange", (-0.43, 0.22, 0.03), (0.0, 0.0, 0.02), (0.035, 0.2), 11.0, rgb=orange)
    # Deep blue rather than the tube's cyan: cyan light turns the orange band yellow.
    S.area(lights, "Rim_Blue", (0.47, 0.26, 0.03), (0.0, 0.0, 0.02), (0.035, 0.2), 7.0, rgb=(0.02, 0.16, 1.0))
    fr = S.fresnel(lights, M, "Fresnel", (-0.36, -0.42, 0), (0.0, 0.03, 0.02), height=0.3, power=12.0)
    # An edge light on the Fresnel itself, so the lamp reads against the dark.
    frim = S.area(lights, "Rim_Fresnel", (-0.14, -0.62, 0.48), (-0.36, -0.42, 0.28), (0.12, 0.12), 5.0,
                  rgb=(1.0, 0.62, 0.35))
    S.link_to(frim, [bpy.data.objects[n] for n in fr["parts"]], "FresnelOnly")
    S.can_light(lights, M, "Can_Violet", (0.3, 0.46, 0), (0.14, 0.14, 0.0), (0.42, 0.22, 1.0), power=6.0)
    S.area(lights, "Fill_Top", (0.05, -0.12, 0.9), (0, 0, 0), (0.7, 0.5), 2.6, rgb=(0.95, 0.97, 1.0))
    S.area(lights, "Fill_Front", (0.25, -0.9, 0.35), (0, 0, 0.03), (0.6, 0.35), 3.5, rgb=(1.0, 0.95, 0.9))
    # A soft light that reaches only into the open pedal, so its insides read.
    inner = S.area(lights, "Fill_Inside", (half + 0.02, -0.06, 0.34), (half, 0.004, 0.0), (0.16, 0.12), 4.5,
                   rgb=(1.0, 0.97, 0.93))
    S.link_to(inner, [ped_open], "OpenPedalOnly")

    cams = U.collection("Cameras", set_)
    tgt = Vector((0, 0.0, 0.02))
    cl = Vector((-half, 0.0, 0.03))
    op = Vector((half, 0.0, 0.025))

    def enc(p, which):
        """Pedal-local mm to world metres."""
        c = -half if which == "closed" else half
        return Vector((c + (p[0] - L.CX) / 1000, (p[1] - L.CY) / 1000, (p[2] + FOOT) / 1000))
    win = enc((*L.WINDOW_C, L.ENC["H"]), "closed")
    S.camera(cams, "CAM_1_Hero", (-0.28, -0.60, 0.2), (0.02, 0.05, 0.03), lens=40, fstop=8.0,
             focus=cl + Vector((0, -0.02, 0)))["exposure"] = -0.3
    S.camera(cams, "CAM_2_Overhead", (0.0, -0.18, 0.78), (0.0, 0.0, 0.0), lens=55, fstop=11.0, focus=tgt)
    S.camera(cams, "CAM_3_Inside", (half + 0.10, -0.22, 0.27), op + Vector((0.0, 0.008, 0.0)), lens=70, fstop=8.0)
    S.camera(cams, "CAM_4_Face", (-half - 0.07, -0.25, 0.17), win + Vector((0.004, -0.004, 0)), lens=70, fstop=8.0,
             focus=win)
    S.camera(cams, "CAM_5_Rear", (0.34, 0.5, 0.2), (0.0, 0.02, 0.02), lens=50, fstop=8.0, focus=op + Vector((0, 0.05, 0)))
    S.camera(cams, "CAM_6_Wide", (0.22, -1.28, 0.4), (-0.05, 0.04, 0.1), lens=32, fstop=8.0, focus=tgt)["exposure"] = 0.0
    S.camera(cams, "CAM_7_Boards", enc((215, -75, 200), "open"), enc((140, 62, 12), "open"), lens=45, fstop=8.0)
    bpy.context.scene.camera = bpy.data.objects["CAM_1_Hero"]

    for img in bpy.data.images:
        if img.source == "FILE":
            img.pack()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND, compress=True)
    print("SAVED", BLEND)


if __name__ == "__main__":
    main()
